"""
Long-lived Server-Sent Events views. These are the only async code in the
ops site: they wait on the event bus and push re-rendered fragments.
"""

import asyncio
import logging
from contextlib import aclosing

from asgiref.sync import sync_to_async
from datastar_py.django import (
    DatastarResponse,
    ServerSentEventGenerator as SSE,
    read_signals,
)
from django.contrib.auth.views import redirect_to_login
from django.db import close_old_connections
from django.http import Http404, HttpResponseForbidden
from django.utils import timezone

from tournamentcontrol.competition.compops import events
from tournamentcontrol.competition.compops.days import parse_day
from tournamentcontrol.competition.compops.default_settings import (
    EVENTS_KEEPALIVE,
    SCOREBOARD_SYNC,
)
from tournamentcontrol.competition.compops.permissions import (
    can_commentate,
    can_score,
)
from tournamentcontrol.competition.compops.scoreboard import SCOPE
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


async def subscribe(season_id, scope=None, idle=None):
    """
    Return the subscription to ``season_id`` in the request's tenant.

    The bus names the channel from the schema of the database connection.
    The tenant middleware points the connection of the request's sync thread
    at the tenant, and the event loop has a connection of its own, so the
    channel is named on the request's thread, before the response starts.

    The subscription ticks when nothing has happened for ``idle`` seconds
    (``EVENTS_KEEPALIVE`` unless given), and the stream then has its say.
    """
    return await sync_to_async(events.subscribe)(
        season_id, idle=float(EVENTS_KEEPALIVE if idle is None else idle), scope=scope
    )


def time_sync():
    """
    The server's time, for a scoreboard's script to set its clock by. The
    clock is counted in the browser; this keeps it from drifting from the
    official time, however long the page has been open.
    """
    now = int(timezone.now().timestamp() * 1000)
    return SSE.execute_script(
        f"window.compopsScoreboard && window.compopsScoreboard.sync({now})"
    )


async def stream(season_id, feed, snapshot, on_event, pulse=None, every=0.0):
    """
    Yield the snapshot, then a patch for every event of the subscription
    ``feed``, with keep-alive comments while idle. ``snapshot`` and
    ``on_event`` are sync callables run through ``sync_to_async`` (thread
    sensitive, so they share the request's database connection semantics).

    The subscription is registered before the snapshot is rendered, and
    yields a ready tick as soon as it is, so an event published while the
    snapshot renders is queued rather than lost.

    A push that fails to render is logged and skipped so one bad event does
    not end every open stream; the snapshot is left to fail loudly.

    With ``pulse``, its event is sent too whenever ``every`` seconds have
    gone by since the last one, whatever else the stream is doing.
    """
    ready = False
    # The loop's clock: the one its waits are timed by.
    clock = asyncio.get_running_loop().time
    pulsed = clock()
    try:
        async with aclosing(feed):
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
                if pulse is not None and clock() - pulsed >= every:
                    pulsed = clock()
                    yield pulse()
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

        feed = await subscribe(season.pk)
        return DatastarResponse(
            stream(season.pk, feed, snapshot, on_event), headers=SSE_HEADERS
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
        allowed = await sync_to_async(can_commentate)(user, season)
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

        feed = await subscribe(season.pk)
        return DatastarResponse(
            stream(season.pk, feed, snapshot, on_event), headers=SSE_HEADERS
        )

    return view


def scoreboard_events(site):
    async def view(request, competition, season, ground):
        season = await get_season(competition, season)
        ground = await site.scoreboard_ground(season, ground)
        # A board is for anyone to see. The scorer's page says that it is
        # one, and is sent its own copy, with the buttons.
        signals = read_signals(request) or {}
        scorer = signals.get("board") == "scorer"
        if scorer:
            user = await request.auser()
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not await sync_to_async(can_score)(user, season):
                return HttpResponseForbidden()

        def snapshot():
            return site.scoreboard_fragments(request, season, ground, scorer)

        def on_event(event):
            # Every ground of the season shares the channel. A score is one
            # ground's; a venue's timekeeper starts the clocks of them all.
            if (
                event.get("ground") != ground.pk
                and event.get("venue") != ground.venue_id
            ):
                return []
            return snapshot()

        every = float(SCOREBOARD_SYNC)
        feed = await subscribe(season.pk, scope=SCOPE, idle=every)
        return DatastarResponse(
            stream(season.pk, feed, snapshot, on_event, time_sync, every),
            headers=SSE_HEADERS,
        )

    return view
