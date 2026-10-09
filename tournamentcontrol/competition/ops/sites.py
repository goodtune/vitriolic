"""
Tournament Ops: a mountable site for running a tournament day.

Mount it from a project's urls.py::

    from tournamentcontrol.competition.ops.sites import OpsSite
    urlpatterns += [path("ops/", OpsSite().urls)]
"""

import datetime
import logging
from functools import wraps

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import include, path, re_path, reverse
from django.utils import timezone

from touchtechnology.common.sites import Application
from tournamentcontrol.competition.models import Season
from tournamentcontrol.competition.ops import events, queries, receivers
from tournamentcontrol.competition.ops.fragments import render_fragment
from tournamentcontrol.competition.ops.permissions import (
    can_stream,
    staff_required,
)
from tournamentcontrol.competition.ops.responses import fragment_response

logger = logging.getLogger(__name__)


def parse_day(datestr):
    try:
        return datetime.datetime.strptime(datestr, "%Y%m%d").date()
    except ValueError:
        raise Http404("Invalid date.")


def season_view(view):
    """
    Resolve the competition and season slugs (and the day, when present)
    before calling the view as ``view(self, request, season, day, **kwargs)``.
    """

    @wraps(view)
    def wrapper(self, request, competition, season, datestr=None, **kwargs):
        season = get_object_or_404(
            Season.objects.select_related("competition").defer(
                "live_stream_thumbnail_image"
            ),
            slug=season,
            competition__slug=competition,
        )
        day = parse_day(datestr) if datestr else None
        return view(self, request, season, day, **kwargs)

    return wrapper


def day_kwargs(season, day):
    return {
        "competition": season.competition.slug,
        "season": season.slug,
        "datestr": day.strftime("%Y%m%d"),
    }


class OpsSite(Application):
    def __init__(self, name="ops", app_name="ops", **kwargs):
        super().__init__(name=name, app_name=app_name, **kwargs)
        receivers.connect()

    # --- urls -------------------------------------------------------

    def get_urls(self):
        return [
            path("", self.index, name="index"),
            path("<slug:competition>/<slug:season>/", include(self.season_urls())),
        ]

    def season_urls(self):
        return [
            path("", self.season, name="season"),
            re_path(r"^(?P<datestr>\d{8})/$", self.day, name="day"),
            re_path(r"^(?P<datestr>\d{8})/", include(self.day_urls())),
        ]

    def day_urls(self):
        return [
            path("results/", self.results, name="results"),
            path("scorers/", self.scorers, name="scorers"),
            path("streams/", self.streams, name="streams"),
            path("activity/", self.activity, name="activity"),
            # Placeholder so the day page can reverse its event stream; the
            # SSE task replaces it with the long-lived stream view.
            path("events/", self.events, name="events"),
        ]

    # --- context ----------------------------------------------------

    def day_context(self, request, season, day):
        now = timezone.now()
        streams, stream_events = queries.day_streams(season, day, now)
        slots = queries.day_results(season, day)
        scorers = list(queries.day_scorers(season, day))
        return {
            "season": season,
            "day": day,
            "daystr": day.strftime("%Y%m%d"),
            "slots": slots,
            "results_pending": sum(s.total - s.entered for s in slots if not s.is_byes),
            "scorers": scorers,
            "streams": streams,
            "live_count": sum(
                1
                for s in streams
                if s.current and s.current.live_stream_status == "live"
            ),
            "events": stream_events,
            "activity": events.recent(season.pk),
            "collapsed": request.session.get("ops_collapsed", False),
            "can_stream": can_stream(request.user, season),
            "user": request.user,
        }

    # --- pages ------------------------------------------------------

    @staff_required
    def index(self, request):
        today = timezone.now().date()
        window = (
            today - datetime.timedelta(days=1),
            today + datetime.timedelta(days=1),
        )
        seasons = list(
            Season.objects.filter(
                enabled=True, divisions__stages__matches__date__range=window
            )
            .select_related("competition")
            .defer("live_stream_thumbnail_image")
            .distinct()
            .order_by("competition__title", "title")
        )
        if len(seasons) == 1:
            return redirect(self._today_url(seasons[0]))
        return self.render(
            request, self.template_path("index.html"), {"seasons": seasons}
        )

    def _today_url(self, season):
        today = queries.local_today(season, timezone.now())
        return reverse("ops:day", kwargs=day_kwargs(season, today))

    @staff_required
    @season_view
    def season(self, request, season, day, **kwargs):
        return redirect(self._today_url(season))

    @staff_required
    @season_view
    def day(self, request, season, day, **kwargs):
        context = self.day_context(request, season, day)
        return self.render(request, self.template_path("day.html"), context)

    @staff_required
    @season_view
    def events(self, request, season, day, **kwargs):
        return HttpResponse(status=204)

    # --- fragments --------------------------------------------------

    @staff_required
    @season_view
    def results(self, request, season, day, **kwargs):
        context = self.day_context(request, season, day)
        return fragment_response(
            request, render_fragment(request, "results", **context)
        )

    @staff_required
    @season_view
    def scorers(self, request, season, day, **kwargs):
        context = self.day_context(request, season, day)
        return fragment_response(
            request, render_fragment(request, "scorers", **context)
        )

    @staff_required
    @season_view
    def streams(self, request, season, day, **kwargs):
        context = self.day_context(request, season, day)
        return fragment_response(
            request, render_fragment(request, "streams", **context)
        )

    @staff_required
    @season_view
    def activity(self, request, season, day, **kwargs):
        context = self.day_context(request, season, day)
        return fragment_response(
            request, render_fragment(request, "activity", **context)
        )
