import collections
import logging
import warnings

import django
from django.conf import settings
from django.conf.urls import include, url
from django.contrib.admin.sites import (
    AdminSite as DjangoAdminSite, AlreadyRegistered, NotRegistered,
)
from django.core.urlresolvers import reverse_lazy
from django.db import connection
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.utils.deprecation import RemovedInNextVersionWarning
from django.utils.encoding import smart_str
from django.utils.translation import ugettext_lazy as _
from touchtechnology.common.decorators import staff_login_required_m
from touchtechnology.common.models import SitemapNode

logger = logging.getLogger(__name__)


class AdminSite(DjangoAdminSite):

    def __init__(self, name='admin', app_name='admin'):
        if django.VERSION[:2] > (1, 7):
            super(AdminSite, self).__init__(name)
        else:
            msg = (
                'AdminSite no longer takes an app_name argument and its '
                'app_name attribute has been removed. The application name '
                'is always admin (as opposed to the instance name which you '
                'can still customize using AdminSite(name="...")'
            )
            warnings.warn(msg, RemovedInNextVersionWarning, stacklevel=2)
            super(AdminSite, self).__init__(name, app_name)
        self._components = collections.OrderedDict()
        self._schemas = collections.defaultdict(lambda: None)

    def register(self, component, *schemas):
        logger.debug("Registering admin component... %s" % component.__name__)
        if component in self._components:
            raise AlreadyRegistered(_(u"The component %s is already "
                                      u"registered" % component.__name__))
        self._components[component] = component(self.name)
        if schemas:
            self._schemas[component] = schemas

    def unregister(self, component):
        self._schemas.pop(component, None)
        try:
            self._components.pop(component)
        except KeyError:
            raise NotRegistered(_(u"The component %s is not "
                                  u"registered" % component.__name__))

    def _hidden_component(self, component):
        schemas = self._schemas[component.__class__]

        if 'tenant_schemas' not in settings.INSTALLED_APPS:
            # Only hide components when we are not in multi-tenant mode
            return False

        if schemas:
            if connection.tenant.schema_name in schemas:
                return False
            return True

        from tenant_schemas.utils import get_public_schema_name
        application = component.__module__.split('.admin', 1)[0]
        logger.debug('application=%r', application)

        # Before we allow it through, make sure the application is available
        # on this tenant.
        if application in settings.INSTALLED_APPS:
            if connection.tenant.schema_name == get_public_schema_name():
                if application not in settings.SHARED_APPS:
                    return True
            else:
                if application not in settings.TENANT_APPS:
                    return True

        return False

    def get_urls(self):
        urlpatterns = [
            url(r'^$', self.index, name='index'),
            url(r'^sitemapnode/move/(?P<id>\d+)/(?P<direction>(up|down))/$',
                self.reorder, name='reorder'),
        ]

        for klass, component in self._components.items():
            # It appears that it is not possible to "hide" a component from
            # the admin URL generation due to this being loaded at startup.
            #
            # Instead we could move this into a middleware like the
            # content.SitemapNodeMiddleware but it might require quite lots of
            # refactoring.
            urlpatterns += [
                url(r'^%s/' % component.name, include(component.urls),
                    {'admin': self, 'component': component}),
            ]

        return urlpatterns

    def get_components(self, show_all=False):
        components = []
        for n, c in self._components.items():
            visible = c.visible or not show_all
            if visible and not self._hidden_component(c):
                components.append((
                    smart_str(c.verbose_name),
                    c.app_name,
                    smart_str(c.reverse('index')),
                    c,
                    self._schemas[n],
                ))
        return components

    def dashboard(self):
        widgets = ()
        for __, __, __, component, schemas in self.get_components():
            try:
                widgets += component.widgets
            except AttributeError:
                pass
        return widgets

    def get_absolute_url(self):
        return self.reverse('index')

    def reverse(self, name, args=None, kwargs=None, prefix=None):
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        named_url = '%s:%s' % (self.name, name)
        if prefix:
            named_url = '%s:%s' % (prefix, named_url)
        return reverse_lazy(named_url, args=args, kwargs=kwargs,
                            current_app=self.name)

    @staff_login_required_m
    def index(self, request, *args, **kwargs):
        context = {'admin': self}
        context.update(kwargs)
        response = TemplateResponse(
            request, 'touchtechnology/admin/index.html', context=context)
        response.current_app = self.name
        return response

    @staff_login_required_m
    def reorder(self, request, id, direction, *args, **kwargs):
        node = get_object_or_404(SitemapNode, pk=id)
        getattr(node, 'move_%s' % direction)()
        redirect_to = request.META.get('HTTP_REFERER', self.reverse('index'))
        return HttpResponseRedirect(redirect_to)
