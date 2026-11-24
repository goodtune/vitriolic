import datetime

from django import template
from django.urls import reverse

from tournamentcontrol.competition.compops.streams import effective_status

register = template.Library()

register.filter("effective_status", effective_status)


@register.filter
def event_time(value):
    """
    An event's ISO 8601 ``at`` string as an aware datetime, so ``time`` can
    show it in the active time zone. Nothing when the value cannot be read.
    """
    try:
        when = datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return when


@register.simple_tag(takes_context=True)
def compops_url(context, name, **kwargs):
    """
    Reverse ``compops:<name>`` with the competition, season and day taken from
    the rendering context, plus any extra keyword arguments.
    """
    season = context["season"]
    params = {"competition": season.competition.slug, "season": season.slug}
    if context.get("daystr"):
        params["datestr"] = context["daystr"]
    params.update(kwargs)
    return reverse(f"compops:{name}", kwargs=params)
