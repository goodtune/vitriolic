from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag(takes_context=True)
def ops_url(context, name, **kwargs):
    """
    Reverse ``ops:<name>`` with the competition, season and day taken from
    the rendering context, plus any extra keyword arguments.
    """
    season = context["season"]
    params = {"competition": season.competition.slug, "season": season.slug}
    if context.get("daystr"):
        params["datestr"] = context["daystr"]
    params.update(kwargs)
    return reverse(f"ops:{name}", kwargs=params)
