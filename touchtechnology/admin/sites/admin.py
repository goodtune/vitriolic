import collections
import logging

from django.conf import settings
from django.contrib.admin.sites import (
    AdminSite as DjangoAdminSite,
    AlreadyRegistered,
    NotRegistered,
)
from django.contrib.auth.views import LogoutView
from django.db import connection
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, re_path, reverse, reverse_lazy
from django.utils.encoding import smart_str
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from guardian.utils import get_40x_or_None

from touchtechnology.admin import explorer
from touchtechnology.admin.branding import get_brand
from touchtechnology.admin.errors import ErrorPages
from touchtechnology.admin.shells import DEFAULT_SHELL, get_shell
from touchtechnology.admin.templatetags.admin import allowed
from touchtechnology.admin.views import AdminLoginView
from touchtechnology.common.decorators import require_POST_m, staff_login_required_m
from touchtechnology.common.models import SitemapNode
from touchtechnology.common.utils import get_perms_for_model

logger = logging.getLogger(__name__)


class AdminSite(DjangoAdminSite):
    def __init__(self, name="admin", shell=DEFAULT_SHELL):
        super().__init__(name)
        self.shell = shell
        self._components = collections.OrderedDict()
        self._schemas = collections.defaultdict(lambda: None)

    @property
    def shell(self):
        """The ``Shell`` the site's pages are drawn by (see ``admin.shells``)."""
        return self._shell

    @shell.setter
    def shell(self, shell):
        # A name, as the constructor takes it. ``ImproperlyConfigured`` for any
        # shell the admin does not ship.
        self._shell = get_shell(getattr(shell, "name", shell))

    def register(self, component, *schemas):
        logger.debug("Registering admin component... %s", component.__name__)
        if component in self._components:
            # During testing, apps can be reloaded causing re-registration
            # Only raise if not explicitly in test mode
            if not getattr(settings, "TESTING", False):
                raise AlreadyRegistered(
                    _("The component %s is already registered") % component.__name__
                )
            else:
                logger.debug(
                    "Component %s already registered, skipping during test",
                    component.__name__,
                )
                return
        instance = component(self.name)
        # The name roots the component's addresses and its ids in the rail,
        # so two components may not share one.
        for registered, other in self._components.items():
            if other.name == instance.name:
                raise AlreadyRegistered(
                    _(
                        "The component %(component)s has the name %(name)s of "
                        "the registered component %(registered)s"
                    )
                    % {
                        "component": component.__name__,
                        "name": instance.name,
                        "registered": registered.__name__,
                    }
                )
        self._components[component] = instance
        instance.admin_site = self
        if schemas:
            self._schemas[component] = schemas

    def unregister(self, component):
        self._schemas.pop(component, None)
        try:
            self._components.pop(component)
        except KeyError:
            raise NotRegistered(
                _("The component %s is not registered") % component.__name__
            )

    def _hidden_component(self, component):
        if "tenant_schemas" not in settings.INSTALLED_APPS:
            # Only hide components when we are not in multi-tenant mode
            return False

        get_public_schema_name = import_string(
            "tenant_schemas.utils.get_public_schema_name"
        )

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

    @property
    def urls(self):
        # Django's is ``self.get_urls(), "admin", self.name``. The patterns are
        # the same, but the site answers what its views refuse with its own
        # pages (see ``admin.errors``) rather than the public site's.
        return [ErrorPages(self.get_urls(), self)], "admin", self.name

    def get_urls(self):
        urlpatterns = [
            path("", self.index, name="index"),
            path(
                "login/",
                AdminLoginView.as_view(extra_context={"admin": self}),
                name="login",
            ),
            path(
                "logout/",
                LogoutView.as_view(next_page=reverse_lazy(f"{self.name}:login")),
                name="logout",
            ),
            path("explorer/", self.explorer, name="explorer"),
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

    def dashboard(self, request):
        """
        The widgets of the home page: those of the components the menu shows
        ``request.user`` (see ``allowed``), so the page draws nothing from an
        application the person may not use, and of those only the widgets with
        something to show (``DashboardWidget.show``).
        """
        widgets = ()
        for __, __, __, component, __ in allowed(self.get_components(), request):
            widgets += tuple(
                widget
                for widget in getattr(component, "widgets", ())
                if widget.show()
            )
        return widgets

    def get_absolute_url(self):
        return self.reverse("index")

    def reverse(self, name, args=None, kwargs=None, prefix=None):
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        named_url = f"{self.name}:{name}"
        if prefix:
            named_url = f"{prefix}:{named_url}"
        return reverse_lazy(named_url, args=args, kwargs=kwargs, current_app=self.name)

    @staff_login_required_m
    def index(self, request, *args, **kwargs):
        context = {"admin": self, "widgets": self.dashboard(request)}
        context.update(kwargs)
        if "brand" not in context:
            context["brand"] = get_brand(request)
        context.setdefault("shell", self.shell)
        context.setdefault("field_template", self.shell.field_template)
        response = TemplateResponse(
            request, self.shell.template("index.html"), context=context
        )
        response.current_app = self.name
        return response

    @staff_login_required_m
    def explorer(self, request, *args, **kwargs):
        """
        A part of the tree in the rail, for the browser to fetch when a folder
        is opened (``mode=tree``, the default) or when the phone's drill-down
        moves to another folder (``mode=drill``). The node is a key
        ``<component>/<local>``, see ``touchtechnology.admin.explorer``.
        """
        node = request.GET.get("node", "")
        name, __, local = node.partition("/")
        components = allowed(self.get_components(), request)
        component = next(
            (c for __, __, __, c, __ in components if c.name == name), None
        )
        if component is None:
            raise Http404("No such part of the tree.")
        context = {"admin": self, "component": component, "shell": self.shell}
        if request.GET.get("mode") == "drill":
            context["tree"] = explorer.drill(request, component, local)
            template = self.shell.template("explorer/drill.html")
        else:
            context["nodes"] = component.explorer().children(request, local)
            context["parent_key"] = node
            template = self.shell.template("explorer/nodes.html")
        response = TemplateResponse(request, template, context=context)
        response.current_app = self.name
        response["Cache-Control"] = "private, no-store"
        return response

    @staff_login_required_m
    @require_POST_m
    def reorder(self, request, id, direction, *args, **kwargs):
        node = get_object_or_404(SitemapNode, pk=id)
        # Only a person who may change the node may move it, as with the
        # Edit item beside its arrows.
        has_permission = get_40x_or_None(
            request,
            get_perms_for_model(SitemapNode, change=True),
            obj=node,
            return_403=True,
            accept_global_perms=True,
        )
        if has_permission is not None:
            return has_permission
        getattr(node, f"move_{direction}")()
        # Back to the list of the folder the node is in.
        query = {"r": node.parent_id} if node.parent_id else None
        return HttpResponseRedirect(
            reverse(f"{self.name}:content:index", query=query, current_app=self.name)
        )
