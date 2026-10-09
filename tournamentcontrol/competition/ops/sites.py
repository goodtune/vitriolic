"""
Tournament Ops: a mountable site for running a tournament day.

Mount it from a project's urls.py::

    from tournamentcontrol.competition.ops.sites import OpsSite
    urlpatterns += [path("ops/", OpsSite().urls)]
"""

import datetime
import logging
from functools import wraps

from django import forms
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import include, path, re_path, reverse
from django.utils import timezone

from touchtechnology.common.decorators import require_POST_m
from touchtechnology.common.sites import Application
from tournamentcontrol.competition.forms import MatchResultForm, MatchStatisticFormset
from tournamentcontrol.competition.models import Season, SimpleScoreMatchStatistic
from tournamentcontrol.competition.ops import events, queries, receivers, streams
from tournamentcontrol.competition.ops.fragments import (
    render_counts,
    render_fragment,
)
from tournamentcontrol.competition.ops.permissions import (
    can_change_match,
    can_enter_statistics,
    can_stream,
    require,
    staff_required,
)
from tournamentcontrol.competition.ops.responses import (
    fragment_response,
    is_datastar,
    patches,
)
from tournamentcontrol.competition.utils import FauxQueryset

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


def style_result_form(form):
    """Give a ``MatchResultForm``'s widgets the ops markup."""
    for side in ("home_team_score", "away_team_score"):
        if side in form.fields:
            team = getattr(form.instance, side.replace("_score", ""))
            widget = form.fields[side].widget
            widget.input_type = "number"
            widget.attrs.update({"class": "sc", "placeholder": team.title[:3].upper()})
            if form.instance.home_team_score is not None:
                widget.attrs["data-preserve-attr"] = "value"
    # The model form renders these as Yes/No selects; a row wants a checkbox.
    for name in ("is_forfeit", "bye_processed"):
        if name in form.fields:
            form.fields[name] = forms.BooleanField(
                required=False, label=form.fields[name].label
            )
    for name, css in (
        ("forfeit_winner", "ff"),
        ("is_forfeit", "ff-check"),
        ("bye_processed", "bye"),
    ):
        if name in form.fields:
            form.fields[name].widget.attrs["class"] = css
    return form


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
            path("results/<str:slot_key>/", self.slot, name="slot"),
            path(
                "results/match/<int:match_pk>/", self.match_result, name="match-result"
            ),
            path(
                "results/match/<int:match_pk>/edit/",
                self.match_result_edit,
                name="match-result-edit",
            ),
            path(
                "scorers/match/<int:match_pk>/",
                self.match_scorers,
                name="match-scorers",
            ),
            path(
                "streams/match/<int:match_pk>/<str:status>/",
                self.match_stream,
                name="match-stream",
            ),
            path(
                "streams/event/<str:event_pk>/<str:status>/",
                self.event_stream,
                name="event-stream",
            ),
            path(
                "streams/slot/<str:slot_key>/<str:status>/",
                self.slot_stream,
                name="slot-stream",
            ),
            # Placeholder so the day page can reverse its event stream; the
            # SSE task replaces it with the long-lived stream view.
            path("events/", self.events, name="events"),
        ]

    # --- context ----------------------------------------------------

    def day_context(self, request, season, day):
        now = timezone.now()
        ground_streams, stream_events = queries.day_streams(season, day, now)
        slots = queries.day_results(season, day)
        for slot in slots:
            for match in slot.matches:
                match.ops_entered = queries.has_result(match)
                match.ops_editable = queries.editable(match) and can_change_match(
                    request.user, match
                )
                match.ops_form = None
                if match.ops_editable and not match.ops_entered:
                    match.ops_form = style_result_form(MatchResultForm(instance=match))
        scorers = list(queries.day_scorers(season, day))
        return {
            "season": season,
            "day": day,
            "daystr": day.strftime("%Y%m%d"),
            "slots": slots,
            "results_pending": sum(s.total - s.entered for s in slots if not s.is_byes),
            "scorers": scorers,
            "streams": ground_streams,
            "stream_errors": [],
            "current_slot": next((s for s in slots if s.open), None),
            "live_count": sum(
                1
                for s in ground_streams
                if s.current and s.current.live_stream_status == "live"
            ),
            "events": stream_events,
            "activity": events.recent(season.pk),
            "collapsed": request.session.get("ops_collapsed", False),
            "can_stream": can_stream(request.user, season),
            "can_statistics": can_enter_statistics(request.user),
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

    # --- results ----------------------------------------------------

    def _day_match(self, season, day, match_pk):
        return get_object_or_404(queries.day_matches(season, day), pk=match_pk)

    def _row_context(self, request, season, day, match, form=None):
        return {
            "season": season,
            "daystr": day.strftime("%Y%m%d"),
            "match": match,
            "form": form,
            "editable": queries.editable(match)
            and can_change_match(request.user, match),
            "entered": queries.has_result(match),
        }

    def slot_patches(self, request, season, day, match):
        """Every fragment a change to ``match`` can alter, re-rendered."""
        context = self.day_context(request, season, day)
        slot = next(
            (s for s in context["slots"] if any(m.pk == match.pk for m in s.matches)),
            None,
        )
        fragments = []
        if slot is not None:
            fragments.append(render_fragment(request, "slot", slot=slot, **context))
        fragments.extend(render_counts(request, **context))
        fragments.append(render_fragment(request, "scorers", **context))
        fragments.append(render_fragment(request, "activity", **context))
        return fragments

    @staff_required
    @season_view
    def slot(self, request, season, day, slot_key, **kwargs):
        context = self.day_context(request, season, day)
        slot = next((s for s in context["slots"] if s.key == slot_key), None)
        if slot is None:
            raise Http404("No such slot.")
        return fragment_response(
            request, render_fragment(request, "slot", slot=slot, **context)
        )

    @staff_required
    @season_view
    def match_result_edit(self, request, season, day, match_pk, **kwargs):
        match = self._day_match(season, day, match_pk)
        require(can_change_match(request.user, match))
        form = style_result_form(MatchResultForm(instance=match))
        html = render_fragment(
            request,
            "match_row",
            editing=True,
            **self._row_context(request, season, day, match, form),
        )
        return fragment_response(request, html)

    @staff_required
    @season_view
    def match_result(self, request, season, day, match_pk, **kwargs):
        match = self._day_match(season, day, match_pk)
        if request.method != "POST":
            context = self._row_context(request, season, day, match)
            if context["editable"] and not context["entered"]:
                context["form"] = style_result_form(MatchResultForm(instance=match))
            html = render_fragment(request, "match_row", **context)
            return fragment_response(request, html)

        require(can_change_match(request.user, match))
        if not queries.editable(match):
            return HttpResponseBadRequest("This match cannot be entered here.")

        form = style_result_form(MatchResultForm(data=request.POST, instance=match))
        form.actor = request.user.get_username()
        form.adjusted = queries.has_result(match)
        redirect_to = reverse("ops:day", kwargs=day_kwargs(season, day))
        if form.is_valid():
            form.save()
            logger.info("ops result saved for match %s by %s", match.pk, form.actor)
            match.refresh_from_db()
            return patches(
                request,
                self.slot_patches(request, season, day, match),
                redirect_to=redirect_to,
            )
        html = render_fragment(
            request,
            "match_row",
            editing=True,
            **self._row_context(request, season, day, match, form),
        )
        return patches(request, [html], redirect_to=redirect_to)

    # --- scorers ----------------------------------------------------

    def statistic_formsets(self, request, match, data=None):
        def roster(team):
            stats = FauxQueryset(SimpleScoreMatchStatistic, team=team)
            for player in team.people.filter(is_player=True).select_related("person"):
                try:
                    statistic = SimpleScoreMatchStatistic.objects.get(
                        match=match, player=player.person
                    )
                except SimpleScoreMatchStatistic.DoesNotExist:
                    statistic = SimpleScoreMatchStatistic(
                        match=match,
                        player=player.person,
                        number=player.number,
                        played=1,
                    )
                stats.append(statistic)
            return stats

        home = MatchStatisticFormset(
            match.home_team_score,
            data=data,
            prefix="home",
            queryset=roster(match.home_team),
        )
        away = MatchStatisticFormset(
            match.away_team_score,
            data=data,
            prefix="away",
            queryset=roster(match.away_team),
        )
        for formset, side in ((home, "home"), (away, "away")):
            for form in formset.forms:
                for name in ("number", "points", "mvp"):
                    form.fields[name].widget.input_type = "number"
                    form.fields[name].widget.attrs["class"] = "st-num"
                form.fields["points"].widget.attrs["data-side"] = side
            formset.allocated = sum(self._allocated(form) for form in formset.forms)
        return home, away

    @staticmethod
    def _allocated(form):
        """The points a roster row currently holds, bound or saved."""
        if form.is_bound:
            value = form["points"].value()
            try:
                return int(value) if value not in (None, "") else 0
            except (TypeError, ValueError):
                return 0
        return form.instance.points or 0

    @staff_required
    @season_view
    def match_scorers(self, request, season, day, match_pk, **kwargs):
        match = get_object_or_404(queries.day_scorers(season, day), pk=match_pk)
        require(can_enter_statistics(request.user))
        day_url = reverse("ops:day", kwargs=day_kwargs(season, day))
        if request.method == "POST":
            home, away = self.statistic_formsets(request, match, data=request.POST)
            if home.is_valid() and away.is_valid():
                home.actor = away.actor = request.user.get_username()
                home.save()
                away.save()
                logger.info(
                    "ops statistics saved for match %s by %s", match.pk, home.actor
                )
                context = self.day_context(request, season, day)
                return patches(
                    request,
                    [
                        render_fragment(request, "scorers", **context),
                        *render_counts(request, **context),
                        render_fragment(request, "activity", **context),
                    ],
                    signals={"modal": False},
                    redirect_to=day_url,
                )
        else:
            home, away = self.statistic_formsets(request, match)
        html = render_fragment(
            request,
            "scorers_modal",
            season=season,
            daystr=day.strftime("%Y%m%d"),
            match=match,
            formsets=(home, away),
        )
        if request.method == "POST":
            return patches(request, [html], redirect_to=day_url)
        if not is_datastar(request):
            return HttpResponse(html)
        return patches(request, [html], signals={"modal": True})

    # --- streams ----------------------------------------------------

    def stream_patches(self, request, season, day, errors=()):
        context = self.day_context(request, season, day)
        context["stream_errors"] = list(errors)
        return [
            render_fragment(request, "streams", **context),
            render_fragment(request, "streams_count", **context),
            render_fragment(request, "activity", **context),
        ]

    def _stream_response(self, request, season, day, errors):
        return patches(
            request,
            self.stream_patches(request, season, day, errors),
            redirect_to=reverse("ops:day", kwargs=day_kwargs(season, day)),
        )

    def _check_status(self, status):
        if status not in streams.STATUSES:
            raise Http404("Unknown broadcast status.")

    @require_POST_m
    @staff_required
    @season_view
    def match_stream(self, request, season, day, match_pk, status, **kwargs):
        self._check_status(status)
        require(can_stream(request.user, season))
        match = self._day_match(season, day, match_pk)
        error = streams.transition(match, status, request.user.get_username())
        return self._stream_response(request, season, day, [error] if error else [])

    @require_POST_m
    @staff_required
    @season_view
    def event_stream(self, request, season, day, event_pk, status, **kwargs):
        self._check_status(status)
        require(can_stream(request.user, season))
        event = get_object_or_404(season.live_stream_events, pk=event_pk)
        error = streams.transition(event, status, request.user.get_username())
        return self._stream_response(request, season, day, [error] if error else [])

    @require_POST_m
    @staff_required
    @season_view
    def slot_stream(self, request, season, day, slot_key, status, **kwargs):
        self._check_status(status)
        require(can_stream(request.user, season))
        slot = queries.slot_for(season, day, slot_key)
        if slot is None:
            raise Http404("No such slot.")
        errors = []
        for match in slot.matches:
            if match.external_identifier:
                error = streams.transition(match, status, request.user.get_username())
                if error:
                    errors.append(error)
        return self._stream_response(request, season, day, errors)
