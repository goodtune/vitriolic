from django.urls import include, path
from django.utils.translation import gettext_lazy as _

from touchtechnology.admin.base import AdminComponent
from touchtechnology.common.decorators import staff_login_required_m
from tournamentcontrol.highlights.models import BaseTemplate


class HighlightsAdminComponent(AdminComponent):
    """Admin component for managing highlight templates."""

    verbose_name = _("Highlights")
    visible = False
    unprotected = False

    def __init__(self, app, name="highlights", app_name="highlights"):
        super().__init__(app, name, app_name)

    def get_urls(self):
        season_patterns = (
            [
                path("", self.list_season, name="list"),
                path("add/", self.edit_season, name="add"),
                path("<int:pk>/", self.edit_season, name="edit"),
                path("<int:pk>/delete/", self.delete_season, name="delete"),
            ],
            self.app_name,
        )

        base_patterns = (
            [
                path("", self.list_base, name="list"),
                path("add/", self.edit_base, name="add"),
                path("<int:template_id>/", self.edit_base, name="edit"),
                path("<int:template_id>/delete/", self.delete_base, name="delete"),
                path(
                    "<int:template_id>/season/",
                    include(season_patterns, namespace="seasontemplate"),
                ),
            ],
            self.app_name,
        )

        return [
            path("", self.index, name="index"),
            path("templates/", include(base_patterns, namespace="basetemplate")),
        ]

    def dropdowns(self):
        return (
            (_("Base templates"), self.reverse("basetemplate:list"), "image"),
            (_("Season templates"), self.reverse("seasontemplate:list"), "image"),
        )

    @staff_login_required_m
    def index(self, request, **kwargs):
        return self.redirect(self.reverse("basetemplate:list"))

    @staff_login_required_m
    def list_base(self, request, **extra_context):
        return self.generic_list(request, BaseTemplate, extra_context=extra_context)

    @staff_login_required_m
    def edit_base(self, request, template_id=None, **extra_context):
        return self.generic_edit(
            request,
            BaseTemplate,
            pk=template_id,
            form_fields=["name", "slug", "template_type", "svg"],
            post_save_redirect=self.redirect(self.reverse("basetemplate:list")),
            extra_context=extra_context,
        )

    @staff_login_required_m
    def delete_base(self, request, template_id, **extra_context):
        return self.generic_delete(request, BaseTemplate, pk=template_id)

    @staff_login_required_m
    def list_season(self, request, template_id, **extra_context):
        return self.generic_list(
            request,
            BaseTemplate.objects.get(pk=template_id).season_templates,
            extra_context=extra_context,
        )

    @staff_login_required_m
    def edit_season(self, request, template_id, pk=None, **extra_context):
        return self.generic_edit(
            request,
            BaseTemplate.objects.get(pk=template_id).season_templates,
            pk=pk,
            form_fields=["season", "name", "config"],
            post_save_redirect=self.redirect(
                self.reverse(
                    "basetemplate:seasontemplate:list",
                    kwargs={"template_id": template_id},
                )
            ),
            extra_context=extra_context,
        )

    @staff_login_required_m
    def delete_season(self, request, template_id, pk, **extra_context):
        return self.generic_delete(
            request,
            BaseTemplate.objects.get(pk=template_id).season_templates,
            pk=pk,
        )
