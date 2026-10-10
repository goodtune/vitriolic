"""
Long-lived Server-Sent Events views. These are the only async code in the
ops site: they wait on the event bus and push re-rendered fragments.
"""

import logging
from contextlib import aclosing

from asgiref.sync import sync_to_async
from datastar_py.django import DatastarResponse
from datastar_py.django import ServerSentEventGenerator as SSE
from datastar_py.django import read_signals
from django.contrib.auth.views import redirect_to_login
from django.db import close_old_connections
from django.http import Http404, HttpResponseForbidden

from tournamentcontrol.competition.compops import events
from tournamentcontrol.competition.compops.days import parse_day
from tournamentcontrol.competition.compops.default_settings import EVENTS_KEEPALIVE
from tournamentcontrol.competition.compops.permissions import can_stream
from tournamentcontrol.competition.models import Season

logger = logging.getLogger(__name__)

SSE_HEADERS = {"Content-Type": "text/event-stream; charset=utf-8"}
KEEPALIVE_LINE = ": ping\n\n"


async def get_season(competition, season):
    try:
        return await (
            Season.objects.select_related("competition")
            .defer("live_stream_thumbnail_image")
            .aget(slug=season, competition__slug=competition)
        )
    except Season.DoesNotExist:
        raise Http404("No such season.")


def render(func, *args):
    """
    Run a sync render on the worker thread with a healthy connection. That
    thread can sit idle for hours between pushes, long enough for the server
    to drop its connection, so validate (or replace) it either side.
    """
    close_old_connections()
    try:
        return func(*args)
    finally:
        close_old_connections()


async def stream(season_id, snapshot, on_event):
    """
    Yield the snapshot, then a patch for every event, with keep-alive
    comments while idle. ``snapshot`` and ``on_event`` are sync callables
    run through ``sync_to_async`` (thread sensitive, so they share the
    request's database connection semantics).

    The subscription is registered before the snapshot is rendered, and
    yields a ready tick as soon as it is, so an event published while the
    snapshot renders is queued rather than lost.

    A push that fails to render is logged and skipped so one bad event does
    not end every open stream; the snapshot is left to fail loudly.
    """
    ready = False
    try:
        async with aclosing(
            events.subscribe(season_id, idle=float(EVENTS_KEEPALIVE))
        ) as feed:
            async for event in feed:
                if not ready:
                    ready = True
                    for html in await sync_to_async(render)(snapshot):
                        yield SSE.patch_elements(html)
                elif event is None:
                    yield KEEPALIVE_LINE
                else:
                    try:
                        fragments = await sync_to_async(render)(on_event, event)
                    except Exception:
                        logger.exception("compops push failed for season %s", season_id)
                        continue
                    for html in fragments:
                        yield SSE.patch_elements(html)
    finally:
        logger.debug("compops stream for season %s closed", season_id)


def compops_events(site):
    async def view(request, competition, season, datestr):
        # The lazy request.user would query the database on first use, which
        # Django refuses on the event loop; auser() resolves it asynchronously.
        user = await request.auser()
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not user.is_staff:
            return HttpResponseForbidden()
        season = await get_season(competition, season)
        day = parse_day(datestr)

        def snapshot():
            return site.snapshot_fragments(request, season, day)

        def on_event(event):
            return site.event_fragments(request, season, day, event)

        return DatastarResponse(
            stream(season.pk, snapshot, on_event), headers=SSE_HEADERS
        )

    return view


def booth_events(site):
    async def view(request, competition, season, ground):
        # The lazy request.user would query the database on first use, which
        # Django refuses on the event loop; auser() resolves it asynchronously.
        user = await request.auser()
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        season = await get_season(competition, season)
        allowed = await sync_to_async(can_stream)(user, season)
        if not allowed:
            return HttpResponseForbidden()
        ground = await site.booth_ground(season, ground)
        # The booth re-issues this request whenever its pane or match
        # changes, so the signals say which pane is open right now.
        signals = read_signals(request) or {}
        pane = signals.get("pane") or "sheets"
        match_pk = signals.get("match")

        def snapshot():
            return site.booth_snapshot(request, season, ground, pane, match_pk)

        def on_event(event):
            return site.booth_event_fragments(
                request, season, ground, pane, match_pk, event
            )

        return DatastarResponse(
            stream(season.pk, snapshot, on_event), headers=SSE_HEADERS
        )

    return view
