from __future__ import unicode_literals

import collections
import logging

from django.conf import settings
from django.contrib.admin.sites import (
    AdminSite as DjangoAdminSite,
    AlreadyRegistered,
    NotRegistered,
)
from django.db import connection
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, re_path, reverse_lazy
from django.utils.encoding import smart_str
from django.utils.translation import gettext_lazy as _

from touchtechnology.common.decorators import staff_login_required_m
from touchtechnology.common.models import SitemapNode

try:
    from tenant_schemas.utils import get_public_schema_name
except ImportError as exc:
    pass

logger = logging.getLogger(__name__)


class AdminSite(DjangoAdminSite):
    def __init__(self, name="admin"):
        super(AdminSite, self).__init__(name)
        self._components = collections.OrderedDict()
        self._schemas = collections.defaultdict(lambda: None)

    def register(self, component, *schemas):
        logger.debug("Registering admin component... %s" % component.__name__)
        if component in self._components:
            raise AlreadyRegistered(
                _("The component %s is already " "registered" % component.__name__)
            )
        self._components[component] = component(self.name)
        if schemas:
            self._schemas[component] = schemas

    def unregister(self, component):
        self._schemas.pop(component, None)
        try:
            self._components.pop(component)
        except KeyError:
            raise NotRegistered(
                _("The component %s is not " "registered" % component.__name__)
            )

    def _hidden_component(self, component):
        if "tenant_schemas" not in settings.INSTALLED_APPS:
            # Only hide components when we are not in multi-tenant mode
            return False

        # For components only registered for specific schemas, return solely
        # based on that option. That is, you can't disable an explicitly
        # registered component for a given schema.
        schemas = self._schemas[component.__class__]
        if schemas:
            if connection.tenant.schema_name in schemas:
                return False
            return True

        application = component.__module__.split(".admin", 1)[0]
        logger.debug("application=%r", application)

        # Before we allow it through, make sure the application is available
        # on this tenant.
        if application in settings.INSTALLED_APPS:
            if connection.tenant.schema_name == get_public_schema_name():
                if application not in settings.SHARED_APPS:
                    return True
            else:
                if application not in settings.TENANT_APPS:
                    return True

        # Lastly, check if the client allows the application in this tenant.
        try:
            return connection.tenant.hidden_component(component)
        except AttributeError:
            return False

    def get_urls(self):
        urlpatterns = [
            path("", self.index, name="index"),
            re_path(
                r"^sitemapnode/move/(?P<id>\d+)/(?P<direction>(up|down))/$",
                self.reorder,
                name="reorder",
            ),
        ]

        for klass, component in self._components.items():
            # It appears that it is not possible to "hide" a component from
            # the admin URL generation due to this being loaded at startup.
            #
            # Instead we could move this into a middleware like the
            # content.SitemapNodeMiddleware but it might require quite lots of
            # refactoring.
            urlpatterns += [
                path(
                    component.name + "/",
                    component.urls,
                    {"admin": self, "component": component},
                ),
            ]

        return urlpatterns

    def get_components(self, show_all=False):
        components = []
        for n, c in self._components.items():
            visible = c.visible or not show_all
            if visible and not self._hidden_component(c):
                components.append(
                    (
                        smart_str(c.verbose_name),
                        c.app_name,
                        smart_str(c.reverse("index")),
                        c,
                        self._schemas[n],
                    )
                )
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
        return self.reverse("index")

    def reverse(self, name, args=None, kwargs=None, prefix=None):
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        named_url = "%s:%s" % (self.name, name)
        if prefix:
            named_url = "%s:%s" % (prefix, named_url)
        return reverse_lazy(named_url, args=args, kwargs=kwargs, current_app=self.name)

    @staff_login_required_m
    def index(self, request, *args, **kwargs):
        context = {"admin": self}
        context.update(kwargs)
        response = TemplateResponse(
            request, "touchtechnology/admin/index.html", context=context
        )
        response.current_app = self.name
        return response

    @staff_login_required_m
    def reorder(self, request, id, direction, *args, **kwargs):
        node = get_object_or_404(SitemapNode, pk=id)
        getattr(node, "move_%s" % direction)()
        redirect_to = request.META.get("HTTP_REFERER", self.reverse("index"))
        return HttpResponseRedirect(redirect_to)
