import logging
import os.path
from importlib.machinery import ModuleSpec
from importlib.util import module_from_spec
from urllib.parse import urlunparse

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.files.storage import default_storage
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.template import RequestContext, TemplateDoesNotExist
from django.urls import include, path, reverse_lazy
from django.utils.deprecation import MiddlewareMixin
from guardian.conf import settings as guardian_settings
from mptt.utils import tree_item_iterator

from touchtechnology.common.default_settings import SITEMAP_HTTPS_OPTION, SITEMAP_ROOT
from touchtechnology.common.models import SitemapNode
from touchtechnology.common.sitemaps import NodeSitemap
from touchtechnology.common.sites import AccountsSite
from touchtechnology.common.views import login
from touchtechnology.content.models import Redirect
from touchtechnology.content.views import dispatch

DEHYDRATED_URLPATTERNS_KEY = "urlpatterns"
DEHYDRATED_URLPATTERNS_TIMEOUT = 600

logger = logging.getLogger(__name__)
protect = AccountsSite(name="protect")


class SitemapNodeMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # When working with multiple tenants, we want to shard the cache for
        # each of them. Use of the version is a nice way to do this as it will
        # prevent collisions while making the API consistent.
        v_kw = {}
        if hasattr(request, "tenant"):
            v_kw.setdefault("version", request.tenant.schema_name)

        # TODO write a cache backend that will do this automatically, and
        #      contribute it back to django-tenant-schemas

        dehydrated = cache.get(DEHYDRATED_URLPATTERNS_KEY, [], **v_kw)

        if not dehydrated:
            logging.getLogger("newrelic.cache").debug("RECALCULATE URLCONF")

            # We need a secret set of account urls so we can bounce the user
            # here if the page is protected. As we haven't yet embedded our
            # url conf (we're in the middle of building it!) this will need
            # to be found using a reverse_lazy below.
            try:
                root = SitemapNode._tree_manager.root_nodes().first()
            except ObjectDoesNotExist:
                root = None
            dehydrated.append(
                {"route": "p/", "site": protect, "kwargs": {"node": root}}
            )

            enabled_nodes = SitemapNode._tree_manager.all()
            related_nodes = enabled_nodes.select_related("content_type")

            def has_disabled_ancestors(st):
                for ancestor in st["ancestors"]:
                    if not ancestor.enabled:
                        return True
                return False

            def get_absolute_url(n, st):
                assert not n.is_root_node()
                offset = 1 if st["ancestors"][0].slug == SITEMAP_ROOT else 0
                paths = [ancestor.slug for ancestor in st["ancestors"][offset:]]
                if paths:
                    return os.path.join(os.path.join(*paths), n.slug)
                return n.slug

            for node, struct in tree_item_iterator(related_nodes, True, lambda x: x):
                # Skip over nodes that they themselves or have disabled ancestors.
                if not node.enabled:
                    logger.debug("%r is disabled, omit from urlconf", node)
                    continue
                if has_disabled_ancestors(struct):
                    logger.debug("%r has disabled ancestor, omit from urlconf", node)
                    continue

                if node.is_root_node() and node.slug == SITEMAP_ROOT:
                    part = ""
                elif node.is_root_node():
                    part = node.slug
                else:
                    part = get_absolute_url(node, struct)

                if part and settings.APPEND_SLASH:
                    part += "/"

                if (
                    node.content_type is not None
                    and node.content_type.model == "placeholder"
                ):
                    try:
                        app = node.object.site(node)
                    except (AttributeError, ImportError, ValueError):
                        logger.exception(
                            "Application is unavailable, disabling this node."
                        )
                        node.disable()
                    else:
                        pattern = {
                            "route": part,
                            "site": app,
                            "kwargs": dict(node=node, **node.kwargs),
                            "name": app.name,
                        }
                        # When nesting applications we need to ensure that any
                        # root url is not clobbered by the patterns of the
                        # parent application. In these cases, force them to the
                        # top of the map.
                        if (
                            node.parent
                            and node.parent.content_type
                            and node.parent.content_type.model == "placeholder"
                        ):
                            dehydrated.insert(0, pattern)
                        else:
                            dehydrated.append(pattern)

                elif node.object_id is None:
                    dehydrated.append(
                        {
                            "route": part,
                            "view": dispatch,
                            "kwargs": dict(node=node, url=part),
                            "name": f"folder_{node.pk}",
                        }
                    )

                else:
                    dehydrated.append(
                        {
                            "route": part,
                            "view": dispatch,
                            "kwargs": dict(page_id=node.object_id, node=node, url=part),
                            "name": f"page_{node.object_id if node.object_id else None}",
                        }
                    )

            cache.set(
                DEHYDRATED_URLPATTERNS_KEY,
                dehydrated,
                timeout=DEHYDRATED_URLPATTERNS_TIMEOUT,
                **v_kw,
            )

        # Always start with the project wide ROOT_URLCONF and add our sitemap.xml view
        urlpatterns = [
            path(
                "sitemap.xml",
                sitemap,
                {"sitemaps": {"nodes": NodeSitemap}},
                name="sitemap",
            ),
            path("", include(settings.ROOT_URLCONF)),
        ]

        # Construct the cache of url pattern definitions. We are not keeping
        # the actual patterns, because pickling is problematic for the .url
        # instancemethod - instead we keep the skeleton and build it on the
        # fly from cache... rehydrating it ;)
        for node in dehydrated:
            try:
                pattern = path(
                    node["route"],
                    node["view"],
                    node["kwargs"],
                    name=node.get("name"),
                )
            except KeyError:
                pattern = path(
                    node["route"],
                    node["site"].urls,
                    node["kwargs"],
                    name=node["site"].name,
                )
            urlpatterns.append(pattern)

        # Create a new module on the fly and attach the rehydrated urlpatterns
        dynamic_urls = module_from_spec(ModuleSpec("dynamic_urls", None))
        dynamic_urls.urlpatterns = urlpatterns

        # Attach the module to the request
        request.urlconf = dynamic_urls

    def process_view(self, request, view_func, view_args, view_kwargs):
        node = view_kwargs.get("node")

        if node:
            required = node.restrict_to_groups.all()

            if required:
                next = node.get_absolute_url()
                to = reverse_lazy("accounts:login")

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
                            response = render(
                                request,
                                guardian_settings.TEMPLATE_403,
                                {},
                                RequestContext(request),
                            )
                            response.status_code = 403
                            return response
                        except TemplateDoesNotExist as e:
                            if settings.DEBUG:
                                raise e
                    elif guardian_settings.RAISE_403:
                        raise PermissionDenied
                    return HttpResponseForbidden()

        if (
            SITEMAP_HTTPS_OPTION
            and node
            and node.require_https
            and not request.is_secure()
        ):
            host = request.META.get("HTTP_HOST")
            path = request.META.get("PATH_INFO")
            redirect_to = urlunparse(("https", host, path, "", "", ""))
            return redirect(redirect_to)


def redirect_middleware(get_response):
    def middleware(request):
        try:
            obj = Redirect.objects.get(source_url__exact=request.path)
        except ObjectDoesNotExist:
            response = get_response(request)
        else:
            response = redirect(obj.destination_url, obj.permanent)
        return response

    return middleware
