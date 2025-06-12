from django.db import models
from django.template import Context, Template

from tournamentcontrol.competition.models import Season

from .constants import HighlightTemplateType


class BaseTemplate(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    template_type = models.CharField(max_length=20, choices=HighlightTemplateType.choices)
    svg = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Highlight template"
        verbose_name_plural = "Highlight templates"

    def __str__(self):
        return self.name

    def render(self, context=None):
        template = Template(self.svg)
        return template.render(Context(context or {}))


class SeasonTemplate(models.Model):
    season = models.ForeignKey(Season, related_name="highlight_templates", on_delete=models.CASCADE)
    base = models.ForeignKey(BaseTemplate, related_name="season_templates", on_delete=models.CASCADE)
    name = models.CharField(max_length=100, blank=True)
    svg = models.TextField(blank=True)
    config = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Season highlight template"
        verbose_name_plural = "Season highlight templates"

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
