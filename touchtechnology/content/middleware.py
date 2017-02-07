import imp
import logging

from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.files.storage import default_storage
from django.core.urlresolvers import reverse_lazy
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render_to_response
from django.template import RequestContext, TemplateDoesNotExist
from django.utils.six.moves.urllib.parse import urlunparse
from guardian.conf import settings as guardian_settings
from touchtechnology.common.default_settings import SITEMAP_HTTPS_OPTION
from touchtechnology.common.models import SitemapNode
from touchtechnology.common.sitemaps import NodeSitemap
from touchtechnology.common.sites import AccountsSite
from touchtechnology.common.views import login
from touchtechnology.content.models import Redirect
from touchtechnology.content.views import dispatch

DEHYDRATED_URLPATTERNS_KEY = 'urlpatterns'
DEHYDRATED_URLPATTERNS_TIMEOUT = 600

logger = logging.getLogger(__name__)
protect = AccountsSite(name="protect")


class SitemapNodeMiddleware(object):

    def process_request(self, request):
        # When working with multiple tenants, we want to shard the cache for
        # each of them. Use of the version is a nice way to do this as it will
        # prevent collisions while making the API consistent.
        v_kw = {}
        if hasattr(request, 'tenant'):
            v_kw.setdefault('version', request.tenant.schema_name)

        # TODO write a cache backend that will do this automatically, and
        #      contribute it back to django-tenant-schemas

        dehydrated = cache.get(DEHYDRATED_URLPATTERNS_KEY, [], **v_kw)

        if not dehydrated:
            logging.getLogger('newrelic.cache').debug('RECALCULATE URLCONF')

            # We need a secret set of account urls so we can bounce the user
            # here if the page is protected. As we haven't yet embedded our
            # url conf (we're in the middle of building it!) this will need
            # to be found using a reverse_lazy below.
            try:
                root = SitemapNode.objects.filter(level=0).latest('lft')
            except ObjectDoesNotExist:
                root = None
            dehydrated.append({
                'regex': r'^p/',
                'site': protect,
                'kwargs': {
                    'node': root,
                },
            })

            enabled_nodes = SitemapNode.objects.filter(enabled=True)
            related_nodes = enabled_nodes.select_related('content_type')

            for node in related_nodes:
                if node.get_ancestors().filter(enabled=False):
                    continue

                path = node.get_absolute_url()[1:]

                if node.content_type is not None and \
                   node.content_type.name == 'placeholder':
                    try:
                        app = node.object.site(node)
                    except (AttributeError, ImportError, ValueError):
                        logger.exception("Application is unavailable, "
                                         "disabling this node.")
                        node.disable()
                    else:
                        pattern = {
                            'regex': r'^%s' % path,
                            'site': app,
                            'kwargs': dict(node=node, **node.kwargs),
                            'name': app.name,
                        }
                        # When nesting applications we need to ensure that any
                        # root url is not clobbered by the patterns of the
                        # parent application. In these cases, force them to the
                        # top of the map.
                        if node.parent and node.parent.content_type and \
                                node.parent.content_type.name == 'placeholder':
                            dehydrated.insert(0, pattern)
                        else:
                            dehydrated.append(pattern)

                elif node.object_id is None:
                    dehydrated.append({
                        'regex': r'^%s$' % path,
                        'view': dispatch,
                        'kwargs': dict(
                            node=node, url=path),
                        'name': 'folder_%d' % node.pk,
                    })

                else:
                    dehydrated.append({
                        'regex': r'^%s$' % path,
                        'view': dispatch,
                        'kwargs': dict(
                            page_id=node.object_id, node=node, url=path),
                        'name': 'page_%d' % (
                            node.object_id if node.object_id else None,),
                    })

            cache.set(DEHYDRATED_URLPATTERNS_KEY, dehydrated,
                      timeout=DEHYDRATED_URLPATTERNS_TIMEOUT,
                      **v_kw)

        # Always start with the project wide ROOT_URLCONF and add our
        # sitemap.xml view
        urlpatterns = [
            url(r'^', include(settings.ROOT_URLCONF)),
            url(r'^sitemap\.xml', sitemap,
                {'sitemaps': {'nodes': NodeSitemap}}, name='sitemap'),
        ]

        # Construct the cache of url pattern definitions. We are not keeping
        # the actual patterns, because pickling is problematic for the .url
        # instancemethod - instead we keep the skeleton and build it on the
        # fly from cache... rehydrating it ;)
        for node in dehydrated:
            try:
                pattern = url(node['regex'], node['view'],
                              node['kwargs'], name=node.get('name'))
            except KeyError:
                pattern = url(node['regex'], include(node['site'].urls),
                              node['kwargs'], name=node['site'].name)
            urlpatterns.append(pattern)

        # For development, add the MEDIA_URL and STATIC_URL to the project
        if settings.DEBUG:
            urlpatterns += static(
                settings.MEDIA_URL,
                document_root=default_storage.path(''),
                show_indexes=True)

            urlpatterns += staticfiles_urlpatterns()

        # Create a new module on the fly and attach the rehydrated urlpatterns
        dynamic_urls = imp.new_module('dynamic_urls')
        dynamic_urls.urlpatterns = urlpatterns

        # Attach the module to the request
        request.urlconf = dynamic_urls

    def process_view(self, request, view_func, view_args, view_kwargs):
        node = view_kwargs.get('node')

        if node:
            required = node.restrict_to_groups.all()

            if required:
                next = node.get_absolute_url()
                to = reverse_lazy('accounts:login')

                # An anonymous user will never be a member of a group, so make
                # them go off and be authenticated.
                if request.user.is_anonymous():
                    return login(request, to=to, next=next)

                # A user who is not a member of a suitable group should get a
                # 403 page.
                groups = request.user.groups.all()
                if set(required).difference(groups):
                    if guardian_settings.RENDER_403:
                        try:
                            response = render_to_response(
                                guardian_settings.TEMPLATE_403, {},
                                RequestContext(request))
                            response.status_code = 403
                            return response
                        except TemplateDoesNotExist as e:
                            if settings.DEBUG:
                                raise e
                    elif guardian_settings.RAISE_403:
                        raise PermissionDenied
                    return HttpResponseForbidden()

        if SITEMAP_HTTPS_OPTION and node and \
           node.require_https and not request.is_secure():
            host = request.META.get('HTTP_HOST')
            path = request.META.get('PATH_INFO')
            redirect_to = urlunparse(
                ('https', host, path, '', '', ''))
            return redirect(redirect_to)


class RedirectMiddleware(object):

    def process_request(self, request):
        try:
            obj = Redirect.objects.get(source_url__exact=request.path)
        except Redirect.DoesNotExist:
            pass
        else:
            return redirect(obj.destination_url, obj.permanent)
