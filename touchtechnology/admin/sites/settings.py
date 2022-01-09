from django.conf import settings
from django.contrib.sites.models import Site
from django.urls import path
from django.utils.translation import gettext_lazy as _

from touchtechnology.admin.base import AdminComponent
from touchtechnology.common.decorators import superuser_login_required_m


class Settings(AdminComponent):
    verbose_name = _("Settings")
    visible = False

    def __init__(self, app, name="settings", app_name="settings"):
        super(Settings, self).__init__(app, name, app_name)

    @property
    def template_base(self):
        return "touchtechnology/admin/settings"

    def get_urls(self):
        urlpatterns = super(Settings, self).get_urls()
        urlpatterns += [
            path("site/", self.edit_site, name="site"),
        ]
        return urlpatterns

    @superuser_login_required_m
    def index(self, request, *args, **kwargs):
        templates = self.template_path("index.html")
        return self.render(request, templates, kwargs)

    @superuser_login_required_m
    def edit_site(self, request, **extra_context):
        tenant = getattr(request, "tenant", None)
        if tenant is not None:
            return self.generic_edit(
                request,
                tenant.__class__,
                instance=tenant,
                form_class=getattr(tenant, "limited_form_class", None),
                extra_context=extra_context,
            )
        return self.generic_edit(
            request, Site, pk=settings.SITE_ID, extra_context=extra_context
        )
