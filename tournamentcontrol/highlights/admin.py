from django.urls import include, path
from django.utils.translation import gettext_lazy as _

from touchtechnology.admin.base import AdminComponent
from touchtechnology.common.decorators import staff_login_required_m

from .models import BaseTemplate, SeasonTemplate
from .forms import BaseTemplateForm, SeasonTemplateForm


class HighlightsAdminComponent(AdminComponent):
    """Admin component for managing highlight templates."""

    verbose_name = _("Highlights")
    unprotected = False

    def __init__(self, app, name="highlights", app_name="highlights"):
        super().__init__(app, name, app_name)

    def get_urls(self):
        base_patterns = (
            [
                path("", self.list_base, name="list"),
                path("add/", self.edit_base, name="add"),
                path("<int:pk>/", self.edit_base, name="edit"),
                path("<int:pk>/delete/", self.delete_base, name="delete"),
            ],
            self.app_name,
        )

        season_patterns = (
            [
                path("", self.list_season, name="list"),
                path("add/", self.edit_season, name="add"),
                path("<int:pk>/", self.edit_season, name="edit"),
                path("<int:pk>/delete/", self.delete_season, name="delete"),
            ],
            self.app_name,
        )

        return [
            path("", self.index, name="index"),
            path("base/", include(base_patterns, namespace="base")),
            path("season/", include(season_patterns, namespace="season")),
        ]

    def dropdowns(self):
        return (
            (_("Base templates"), self.reverse("base:list"), "image"),
            (_("Season templates"), self.reverse("season:list"), "image"),
        )

    @staff_login_required_m
    def index(self, request, **kwargs):
        return self.redirect(self.reverse("base:list"))

    @staff_login_required_m
    def list_base(self, request, **extra_context):
        return self.generic_list(request, BaseTemplate, extra_context=extra_context)

    @staff_login_required_m
    def edit_base(self, request, pk=None, **extra_context):
        return self.generic_edit(
            request,
            BaseTemplate,
            pk=pk,
            form_class=BaseTemplateForm,
            post_save_redirect=self.redirect(self.reverse("base:list")),
            extra_context=extra_context,
        )

    @staff_login_required_m
    def delete_base(self, request, pk, **extra_context):
        return self.generic_delete(request, BaseTemplate, pk=pk)

    @staff_login_required_m
    def list_season(self, request, **extra_context):
        return self.generic_list(request, SeasonTemplate, extra_context=extra_context)

    @staff_login_required_m
    def edit_season(self, request, pk=None, **extra_context):
        return self.generic_edit(
            request,
            SeasonTemplate,
            pk=pk,
            form_class=SeasonTemplateForm,
            post_save_redirect=self.redirect(self.reverse("season:list")),
            extra_context=extra_context,
        )

    @staff_login_required_m
    def delete_season(self, request, pk, **extra_context):
        return self.generic_delete(request, SeasonTemplate, pk=pk)
