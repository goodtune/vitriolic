"""
Long-lived Server-Sent Events views. These are the only async code in the
ops site: they wait on the event bus and push re-rendered fragments.
"""

import logging
from contextlib import aclosing

from asgiref.sync import sync_to_async
from datastar_py.django import DatastarResponse
from datastar_py.django import ServerSentEventGenerator as SSE
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpResponseForbidden

from tournamentcontrol.competition.models import Season
from tournamentcontrol.competition.ops import events

logger = logging.getLogger(__name__)

SSE_HEADERS = {"Content-Type": "text/event-stream; charset=utf-8"}
KEEPALIVE_LINE = ": ping\n\n"


def keepalive():
    return getattr(settings, "OPS_EVENTS_KEEPALIVE", 20)


async def authenticate(request):
    user = await request.auser()
    request.user = user
    return user


async def get_season(competition, season):
    try:
        return await (
            Season.objects.select_related("competition")
            .defer("live_stream_thumbnail_image")
            .aget(slug=season, competition__slug=competition)
        )
    except Season.DoesNotExist:
        raise Http404("No such season.")


async def stream(season_id, snapshot, on_event):
    """
    Yield the snapshot, then a patch for every event, with keep-alive
    comments while idle. ``snapshot`` and ``on_event`` are sync callables
    run through ``sync_to_async`` (thread sensitive, so they share the
    request's database connection semantics).

    The subscription is registered before the snapshot is rendered, and
    yields a ready tick as soon as it is, so an event published while the
    snapshot renders is queued rather than lost.
    """
    ready = False
    try:
        async with aclosing(events.subscribe(season_id, idle=keepalive())) as feed:
            async for event in feed:
                if not ready:
                    ready = True
                    for html in await sync_to_async(snapshot)():
                        yield SSE.patch_elements(html)
                elif event is None:
                    yield KEEPALIVE_LINE
                else:
                    for html in await sync_to_async(on_event)(event):
                        yield SSE.patch_elements(html)
    finally:
        logger.debug("ops stream for season %s closed", season_id)


def ops_events(site):
    async def view(request, competition, season, datestr):
        user = await authenticate(request)
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not user.is_staff:
            return HttpResponseForbidden()
        season = await get_season(competition, season)
        day = site.parse_day(datestr)

        def snapshot():
            return site.snapshot_fragments(request, season, day)

        def on_event(event):
            return site.event_fragments(request, season, day, event)

        return DatastarResponse(
            stream(season.pk, snapshot, on_event), headers=SSE_HEADERS
        )

    return view
