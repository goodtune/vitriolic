from django.db import models
from django.template import Context, Template

from touchtechnology.admin.mixins import AdminUrlMixin
from tournamentcontrol.competition.models import Season
from tournamentcontrol.highlights.constants import HighlightTemplateType


class BaseTemplate(AdminUrlMixin, models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    template_type = models.CharField(
        max_length=20, choices=HighlightTemplateType.choices
    )
    svg = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Template"
        verbose_name_plural = "Templates"

    def __str__(self):
        return self.name

    def render(self, context=None):
        template = Template(self.svg)
        return template.render(Context(context or {}))

    def _get_admin_namespace(self):
        return "admin:highlights:basetemplate"

    def _get_url_args(self):
        return (self.pk,)


class SeasonTemplate(AdminUrlMixin, models.Model):
    season = models.ForeignKey(
        Season, related_name="highlight_templates", on_delete=models.CASCADE
    )
    base = models.ForeignKey(
        BaseTemplate, related_name="season_templates", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=100, blank=True)
    svg = models.TextField(blank=True)
    config = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Season template"
        verbose_name_plural = "Season templates"

    def __str__(self):
        return self.name or f"{self.season}: {self.base.name}"

    def render(self, context=None):
        data = {}
        data.update(self.config)
        if context:
            data.update(context)
        svg = self.svg or self.base.svg
        template = Template(svg)
        return template.render(Context(data))

    def _get_admin_namespace(self):
        return "admin:highlights:season"

    def _get_url_args(self):
        return (self.pk,)
