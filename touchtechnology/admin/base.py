import os.path
from urllib.parse import urlunparse

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.encoding import smart_str
from modelforms.forms import ModelForm

from touchtechnology.admin.branding import get_brand
from touchtechnology.admin.forms import AdminFormControlMixin
from touchtechnology.common.decorators import (
    never_cache_m,
    staff_login_required_m,
)
from touchtechnology.common.default_settings import SITEMAP_HTTPS_OPTION
from touchtechnology.common.forms.mixins import BootstrapFormControlMixin
from touchtechnology.common.sites import Application


class AdminComponentMixin(object):
    verbose_name = "ExampleComponent"
    visible = True
    #: The name of the component's icon in the admin's sprite (``None`` picks
    #: one from the component's ``app_name``).
    icon = None

    # While adding this new functionality, we'll start out with
    # AdminComponents being unprotected by default, even though we typically
    # protect by @staff_login_required_m it's not our intent, we're moving
    # towards the permission's and django-guardian.
    unprotected = True

    def __init__(self, app, name, app_name, *args, **kwargs):
        super(AdminComponentMixin, self).__init__(
            name=name, app_name=app_name, *args, **kwargs
        )
        self.app = app

    @property
    def current_app(self):
        return self.app

    def _template_path(self, filename, *args):
        i = super(AdminComponentMixin, self)._template_path(filename, *args)
        for t in i:
            yield t
        yield os.path.join("touchtechnology/admin", filename)

    @never_cache_m
    @staff_login_required_m
    def render(self, request, templates, context, *args, **kwargs):
        """
        If the site has HTTPS enabled, then we should ensure that this view
        is being served securely; otherwise we can carry on as normal.

        Ensure that the AdminComponent will redirect the user if it is deemed
        to be hidden for this tenant. Will have no impact on single-tenant
        installs.
        """
        if hasattr(request, "tenant"):
            admin = context.get("admin")
            if admin._hidden_component(self):
                messages.error(
                    request,
                    'Attempt to access component "%s" '
                    "is not allowed for this tenant." % smart_str(self.verbose_name),
                )
                return HttpResponseRedirect(reverse("admin:index"))

        if SITEMAP_HTTPS_OPTION and not request.is_secure():
            host = request.META.get("HTTP_HOST")
            path = request.META.get("PATH_INFO")
            redirect_to = urlunparse(("https", host, path, "", "", ""))
            return HttpResponseRedirect(redirect_to)

        # Resolve the brand here so the shell is branded even when the
        # ``brand`` context processor has not been configured.
        if "brand" not in context:
            context["brand"] = get_brand(request)
        context.setdefault(
            "field_template", "touchtechnology/admin/templatetags/field.html"
        )

        return super(AdminComponentMixin, self).render(
            request, templates, context, *args, **kwargs
        )

    def reverse(self, name, args=(), kwargs={}, prefix=None):
        if prefix is None:
            prefix = self.app
        return super(AdminComponentMixin, self).reverse(name, args, kwargs, prefix)

    def tasks(self, request):
        """
        The jobs this component offers on the admin's home page, most common
        first: an iterable of mappings with ``label``, ``url`` and optionally
        ``note`` (a line saying more) and ``icon`` (a name in the admin's icon
        sprite). By default, the first of the component's ``dropdowns``.
        """
        sections = list(self.dropdowns() or ())
        if not sections:
            return ()
        label, url = sections[0][0], sections[0][1]
        return ({"label": label, "url": url, "note": self.verbose_name},)

    def dropdowns(self):
        """
        When implementing your component you should override this method if the
        component is used to manage a number of models or things. For example,
        a component dealing with Users & Groups should return an iterable of
        tuples:

            (name, path, optional font awesome icon name)

        For example:

            [("Users", "/admin/auth/users/", "user"),
             ("Groups", "/admin/auth/groups/", "group")]
        """
        return ()


class AdminComponent(AdminComponentMixin, Application):
    """
    If an AdminComponent does not share any common functionality with a
    front end application, it can just inherit from this for simplicity
    and backwards compatibility.
    """

    model_form_bases = (AdminFormControlMixin, ModelForm)

    def get_required_form_bases(self):
        """
        The bases a form must inherit: ``model_form_bases``, with the common
        ``BootstrapFormControlMixin`` accepted in place of the admin's own mixin
        (which subclasses it), so explicit forms on either satisfy the check.
        A component that overrides ``model_form_bases`` is checked against its
        own bases. Setting ``required_form_bases`` takes precedence.
        """
        if self.required_form_bases is not None:
            return self.required_form_bases
        return tuple(
            BootstrapFormControlMixin if base is AdminFormControlMixin else base
            for base in self.model_form_bases
        )

    def get_urls(self):
        urlpatterns = [
            path("", self.index, name="index"),
        ]
        return urlpatterns

    @property
    def namespace(self):
        """
        If we've subclassed another AdminComponent, chances are we want to
        overload existing templates. We should therefore keep the namespace
        of the oldest parent in the inheritance tree (that is a descendant
        of AdminComponent).
        """
        mro = self.__class__.__mro__
        i = mro.index(AdminComponent)
        return self._get_namespace(mro[i - 1])

    @property
    def template_base(self):
        """
        Our standard template directory for AdminComponent's will be 'admin'
        within the projects normally namespaced template directory.
        """
        return os.path.join(super(AdminComponent, self).template_base, "admin")


class DashboardWidget(object):
    verbose_name = NotImplemented
    template = NotImplemented
    half = True

    @classmethod
    def show(cls):
        return True

    def _get_context(self):
        raise NotImplementedError

    @property
    def context(self):
        return self._get_context()
