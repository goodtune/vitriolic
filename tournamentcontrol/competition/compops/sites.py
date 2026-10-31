"""
Tournament Ops: a mountable site for running a tournament day.

Mount it from a project's urls.py::

    from tournamentcontrol.competition.compops.sites import CompOpsSite
    urlpatterns += [path("compops/", CompOpsSite().urls)]
"""

import datetime
import logging
from functools import wraps

import django
from datastar_py.consts import ElementPatchMode
from django import forms
from django.apps import apps
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import include, path, re_path, reverse
from django.utils import timezone

from touchtechnology.common.decorators import login_required_m, require_POST_m
from touchtechnology.common.sites import Application
from tournamentcontrol.competition.compops import (
    events,
    queries,
    receivers,
    sse,
    streams,
)
from tournamentcontrol.competition.compops.days import day_kwargs, parse_day
from tournamentcontrol.competition.compops.fragments import (
    render_counts,
    render_fragment,
)
from tournamentcontrol.competition.compops.permissions import (
    can_change_match,
    can_enter_statistics,
    can_stream,
    require,
    staff_required,
)
from tournamentcontrol.competition.compops.responses import fragment_response, patches
from tournamentcontrol.competition.forms import MatchResultForm, MatchStatisticFormset
from tournamentcontrol.competition.models import (
    Ground,
    Match,
    Season,
    SimpleScoreMatchStatistic,
    Team,
)
from tournamentcontrol.competition.utils import FauxQueryset

logger = logging.getLogger(__name__)

DATASTAR_MIDDLEWARE = "touchtechnology.common.middleware.DatastarMiddleware"
TEMPLATE_PARTIALS = "template_partials"


def partials_available():
    """
    Template partials are built into Django from 6.0. Before that they come
    from django-template-partials, which must be installed as an app.
    """
    return django.VERSION >= (6, 0) or apps.is_installed(TEMPLATE_PARTIALS)


PANES = ("sheets", "results", "ladder", "leaders")
PANE_LABELS = [
    ("sheets", "Team sheets"),
    ("results", "Results so far"),
    ("ladder", "Ladder"),
    ("leaders", "Tournament leaders"),
]


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


def booth_view(view):
    """
    Resolve the competition, season and (streamed) ground slugs before
    calling the view as ``view(self, request, season, ground, **kwargs)``.
    """

    @wraps(view)
    def wrapper(self, request, competition, season, ground, **kwargs):
        season = get_object_or_404(
            Season.objects.select_related("competition").defer(
                "live_stream_thumbnail_image"
            ),
            slug=season,
            competition__slug=competition,
        )
        ground = (
            Ground.objects.filter(venue__season=season, slug=ground, live_stream=True)
            .select_related("venue")
            .order_by("venue__order", "order")
            .first()
        )
        if ground is None:
            raise Http404("No such streamed ground.")
        return view(self, request, season, ground, **kwargs)

    return wrapper


def booth_required(view):
    """Login plus ``stream_season``; the booth does not need ``is_staff``."""

    @wraps(view)
    def wrapper(self, request, season, ground, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        require(can_stream(request.user, season))
        return view(self, request, season, ground, **kwargs)

    return wrapper


def style_result_form(form):
    """Give a ``MatchResultForm``'s widgets the ops markup."""
    for side in ("home_team_score", "away_team_score"):
        if side in form.fields:
            widget = form.fields[side].widget
            widget.input_type = "number"
            widget.attrs["class"] = "sc"
            # The form hints with the team's name, which the row now shows.
            widget.attrs.pop("placeholder", None)
            # A morph from the event stream must not reset a score being
            # typed, or one a refused post sent back.
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


def result_form(match, data=None):
    """
    A styled ``MatchResultForm`` for ``match``. Its ids carry the match's pk:
    a page holds a form per pending match, and Datastar morphs by id, so
    duplicate ids would pair a typed input with another row's.
    """
    return style_result_form(
        MatchResultForm(data=data, instance=match, auto_id=f"m{match.pk}_%s")
    )


def stream_block(obj):
    """
    The element id of the block of the streams column that shows ``obj``: a
    match's ground's block, a ground's block, or a season event's own.
    """
    if isinstance(obj, Match):
        return f"stream-{obj.play_at_id}"
    if isinstance(obj, Ground):
        return f"stream-{obj.pk}"
    return f"event-{obj.pk}"


def changed_stream(event):
    """The block (as ``stream_block`` names it) a ``stream-changed`` event is about."""
    if event.get("kind") == "event":
        return f"event-{event.get('id')}"
    return f"stream-{event.get('ground')}"


class CompOpsSite(Application):
    def __init__(self, name="compops", app_name="compops", **kwargs):
        super().__init__(name=name, app_name=app_name, **kwargs)
        if DATASTAR_MIDDLEWARE not in settings.MIDDLEWARE:
            raise ImproperlyConfigured(
                f"CompOpsSite needs {DATASTAR_MIDDLEWARE!r} in MIDDLEWARE."
            )
        if not partials_available():
            raise ImproperlyConfigured(
                f"CompOpsSite needs django-template-partials and {TEMPLATE_PARTIALS!r} "
                "in INSTALLED_APPS before Django 6.0."
            )
        receivers.connect()

    @property
    def template_base(self):
        # A module of the competition app, so its templates live under the
        # app's directory rather than under the namespace alone.
        return "tournamentcontrol/competition/compops"

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
            path("booth/", include(self.booth_urls())),
        ]

    def booth_urls(self):
        return [
            path("", self.booth_index, name="booth-index"),
            path("<slug:ground>/", self.booth, name="booth"),
            path("<slug:ground>/lamp/", self.booth_lamp, name="booth-lamp"),
            path("<slug:ground>/strip/", self.booth_strip, name="booth-strip"),
            path("<slug:ground>/events/", sse.booth_events(self), name="booth-events"),
            path(
                "<slug:ground>/onair/<str:status>/",
                self.booth_onair,
                name="booth-onair",
            ),
            path("<slug:ground>/arm/", self.booth_arm, name="booth-arm"),
            path("<slug:ground>/runsheet/", self.booth_runsheet, name="booth-runsheet"),
            path(
                "<slug:ground>/match/<int:match_pk>/teams/",
                self.booth_teams,
                name="booth-teams",
            ),
            path(
                "<slug:ground>/match/<int:match_pk>/<str:pane>/",
                self.booth_pane,
                name="booth-pane",
            ),
            path(
                "<slug:ground>/team/<int:team_pk>/", self.booth_team, name="booth-team"
            ),
        ]

    def day_urls(self):
        return [
            path("results/", self.results, name="results"),
            path("scorers/", self.scorers, name="scorers"),
            path("streams/", self.streams, name="streams"),
            path("activity/", self.activity, name="activity"),
            path("layout/", self.layout, name="layout"),
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
            path("events/", sse.compops_events(self), name="events"),
        ]

    # --- context ----------------------------------------------------

    def day_context(
        self,
        request,
        season,
        day,
        bound_forms=None,
        stream_errors=None,
        keep_held=False,
        changed=None,
    ):
        """
        The context for the day page and its fragments. ``bound_forms`` maps
        a match's pk to a submitted result form to show in place of its own,
        with its errors; ``stream_errors`` maps a block of the streams column
        (see ``stream_block``) to the refusals it shows. ``keep_held`` is for
        a patch of the whole list or column, which must leave the rows and
        blocks the person holds as they are (see ``match_row`` and
        ``ground_stream`` in day.html); ``changed`` names the one block such
        a patch is about, which it releases.
        """
        bound_forms = bound_forms or {}
        stream_errors = stream_errors or {}
        now = timezone.now()
        ground_streams, stream_events = queries.day_streams(season, day, now)
        blocks = [(item, stream_block(item.ground)) for item in ground_streams]
        blocks += [(event, stream_block(event)) for event in stream_events]
        for shown, block in blocks:
            shown.compops_errors = stream_errors.get(block, [])
            shown.compops_held = keep_held and block != changed
        slots = queries.day_results(season, day)
        for slot in slots:
            for match in slot.matches:
                match.compops_entered = match.has_result
                match.compops_editable = match.result_editable and can_change_match(
                    request.user, match
                )
                match.compops_form = None
                match.compops_editing = False
                if match.pk in bound_forms:
                    match.compops_form = bound_forms[match.pk]
                    match.compops_editing = match.compops_entered
                elif match.compops_editable and not match.compops_entered:
                    match.compops_form = result_form(match)
        scorers = list(queries.day_scorers(season, day))
        current_slot, next_slot = self._stream_slots(slots, ground_streams)
        return {
            "season": season,
            "day": day,
            "daystr": day.strftime("%Y%m%d"),
            "slots": slots,
            "results_pending": sum(s.total - s.entered for s in slots if not s.is_byes),
            "scorers": scorers,
            "streams": ground_streams,
            "current_slot": current_slot,
            "next_slot": next_slot,
            "live_count": sum(
                1
                for s in ground_streams
                if s.current
                and streams.effective_status(s.current.live_stream_status) == "live"
            ),
            "events": stream_events,
            "activity": events.recent(season.pk),
            "collapsed": request.session.get("compops_collapsed", False),
            "can_stream": can_stream(request.user, season),
            "can_statistics": can_enter_statistics(request.user),
            "keep_held": keep_held,
            "user": request.user,
        }

    @staticmethod
    def _stream_slots(slots, ground_streams):
        """
        The slots for the whole-slot stream actions, chosen by the clock: the
        latest kick-off on air on any streamed ground and the earliest one to
        come.
        """
        by_key = {s.key: s for s in slots if s.time is not None}

        def slot_of(matches, pick):
            times = [m.time for m in matches if m is not None and m.time]
            if not times:
                return None
            return by_key.get(pick(times).strftime("%H%M"))

        current_slot = slot_of([s.current for s in ground_streams], max)
        next_slot = slot_of([s.next for s in ground_streams], min)
        if next_slot is current_slot:
            next_slot = None
        return current_slot, next_slot

    def snapshot_fragments(self, request, season, day):
        """
        Everything the day page shows that can change, freshly rendered. The
        stream sends it on every reconnect, so it leaves the rows the person
        holds, an open Edit or a refused save, and the blocks of the streams
        column that show a refusal, as they are.
        """
        context = self.day_context(request, season, day, keep_held=True)
        fragments = [
            render_fragment(request, name, **context)
            for name in ("results", "scorers", "streams", "activity")
        ]
        fragments.extend(render_counts(request, **context))
        return fragments

    def event_fragments(self, request, season, day, event):
        """The fragments to push to a subscriber for one bus ``event``."""
        kind = event.get("type")
        if kind in ("score-entered", "bye-processed"):
            match = Match.objects.filter(pk=event.get("match")).first()
            if match is None:
                return []
            return self.slot_patches(request, season, day, match)
        if kind == "statistics-entered":
            context = self.day_context(request, season, day)
            return [
                render_fragment(request, "scorers", **context),
                render_fragment(request, "activity", **context),
                *render_counts(request, **context),
            ]
        if kind == "stream-changed":
            # The push releases the block it is about and leaves the other
            # held blocks as they are; see ground_stream in day.html.
            return self.stream_patches(
                request, season, day, keep_held=True, changed=changed_stream(event)
            )
        return []

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
        today = season.local_date()
        return reverse("compops:day", kwargs=day_kwargs(season, today))

    @staff_required
    @season_view
    def season(self, request, season, day, **kwargs):
        return redirect(self._today_url(season))

    @staff_required
    @season_view
    def day(self, request, season, day, **kwargs):
        return self.day_page(request, season, day)

    def day_page(self, request, season, day, **overrides):
        """The whole day page, as a plain browser gets it."""
        context = self.day_context(request, season, day, **overrides)
        return self.render(request, self.template_path("day.html"), context)

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

    @require_POST_m
    @staff_required
    @season_view
    def layout(self, request, season, day, **kwargs):
        request.session["compops_collapsed"] = not request.session.get(
            "compops_collapsed", False
        )
        context = self.day_context(request, season, day, keep_held=True)
        return patches(
            request,
            [render_fragment(request, "main", **context)],
            redirect_to=reverse("compops:day", kwargs=day_kwargs(season, day)),
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
            "editable": match.result_editable and can_change_match(request.user, match),
            "entered": match.has_result,
        }

    def slot_patches(self, request, season, day, match):
        """
        Every fragment a change to ``match`` can alter, re-rendered: its row
        and its slot's header, not the whole slot, so a score being typed
        into another row of the slot survives the push.
        """
        context = self.day_context(request, season, day)
        slot, fresh = next(
            ((s, m) for s in context["slots"] for m in s.matches if m.pk == match.pk),
            (None, None),
        )
        fragments = []
        if slot is not None:
            row = self._row_context(request, season, day, fresh, fresh.compops_form)
            fragments.append(render_fragment(request, "match_row", **row))
            fragments.append(
                render_fragment(request, "slot_header", slot=slot, **context)
            )
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
        form = result_form(match)
        html = render_fragment(
            request,
            "match_row",
            editing=True,
            **self._row_context(request, season, day, match, form),
        )
        # A held row is sent whole; see match_row in day.html.
        return fragment_response(request, html, mode=ElementPatchMode.REPLACE)

    @staff_required
    @season_view
    def match_result(self, request, season, day, match_pk, **kwargs):
        match = self._day_match(season, day, match_pk)
        if request.method != "POST":
            context = self._row_context(request, season, day, match)
            if context["editable"] and not context["entered"]:
                context["form"] = result_form(match)
            html = render_fragment(request, "match_row", **context)
            return fragment_response(request, html)

        require(can_change_match(request.user, match))
        if not match.result_editable:
            return HttpResponseBadRequest("This match cannot be entered here.")

        form = result_form(match, data=request.POST)
        form.actor = request.user.get_username()
        form.adjusted = match.has_result
        redirect_to = reverse("compops:day", kwargs=day_kwargs(season, day))
        if form.is_valid():
            form.save()
            logger.info("compops result saved for match %s by %s", match.pk, form.actor)
            match.refresh_from_db()
            return patches(
                request,
                self.slot_patches(request, season, day, match),
                redirect_to=redirect_to,
            )
        # A held row is sent whole; see match_row in day.html.
        return patches(
            request,
            lambda: [
                render_fragment(
                    request,
                    "match_row",
                    editing=form.adjusted,
                    **self._row_context(request, season, day, match, form),
                )
            ],
            redirect_to=redirect_to,
            page=lambda: self.day_page(
                request, season, day, bound_forms={match.pk: form}
            ),
            mode=ElementPatchMode.REPLACE,
        )

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
        day_url = reverse("compops:day", kwargs=day_kwargs(season, day))
        if request.method == "POST":
            home, away = self.statistic_formsets(request, match, data=request.POST)
            if home.is_valid() and away.is_valid():
                home.actor = away.actor = request.user.get_username()
                with transaction.atomic():
                    home.save()
                    away.save()
                logger.info(
                    "compops statistics saved for match %s by %s", match.pk, home.actor
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

        def modal(**extra):
            return render_fragment(
                request,
                "scorers_modal",
                season=season,
                daystr=day.strftime("%Y%m%d"),
                match=match,
                formsets=(home, away),
                **extra,
            )

        def page():
            # No JavaScript here: the modal's buttons become links to the day.
            context = {
                "season": season,
                "day": day,
                "daystr": day.strftime("%Y%m%d"),
                "match": match,
                "modal": modal(standalone=True),
                "user": request.user,
            }
            return self.render(request, self.template_path("scorers.html"), context)

        return patches(
            request,
            lambda: [modal()],
            signals=None if request.method == "POST" else {"modal": True},
            redirect_to=day_url,
            page=page,
        )

    # --- streams ----------------------------------------------------

    def stream_patches(self, request, season, day, keep_held=False, changed=None):
        """
        The streams column, the activity and the counts, re-rendered. A push
        leaves the blocks the person holds as they are (``keep_held``) except
        the block ``changed`` names; see ``ground_stream`` in day.html.
        """
        context = self.day_context(
            request, season, day, keep_held=keep_held, changed=changed
        )
        return [
            render_fragment(request, "streams", **context),
            render_fragment(request, "activity", **context),
            *render_counts(request, **context),
        ]

    def refused_stream_patches(self, request, season, day, errors):
        """
        The blocks of the streams column that ``errors`` are about, each held
        with its refusals, and nothing else: a refusal changes nothing else.
        """
        context = self.day_context(request, season, day, stream_errors=errors)
        return [
            render_fragment(request, "ground_stream", item=item, **context)
            for item in context["streams"]
            if item.compops_errors
        ] + [
            render_fragment(request, "season_event", event=event, **context)
            for event in context["events"]
            if event.compops_errors
        ]

    def _stream_response(self, request, season, day, errors):
        """
        Answer a stream action. ``errors`` maps a block of the streams column
        (see ``stream_block``) to its refusals. An action that went through
        sends the column with no block held, which releases them all; a
        refused one sends the refused blocks alone, held and whole (see
        ``ground_stream`` in day.html).
        """
        redirect_to = reverse("compops:day", kwargs=day_kwargs(season, day))
        if not errors:
            return patches(
                request,
                lambda: self.stream_patches(request, season, day),
                redirect_to=redirect_to,
            )
        return patches(
            request,
            lambda: self.refused_stream_patches(request, season, day, errors),
            redirect_to=redirect_to,
            page=lambda: self.day_page(request, season, day, stream_errors=errors),
            mode=ElementPatchMode.REPLACE,
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
        if not streams.opted_in(match, streams.streamed_ground_ids(season)):
            raise Http404("The match is not streamed.")
        error = streams.transition(match, status, request.user.get_username())
        return self._stream_response(
            request, season, day, {stream_block(match): [error]} if error else {}
        )

    @require_POST_m
    @staff_required
    @season_view
    def event_stream(self, request, season, day, event_pk, status, **kwargs):
        self._check_status(status)
        require(can_stream(request.user, season))
        event = get_object_or_404(queries.day_events(season, day), pk=event_pk)
        error = streams.transition(event, status, request.user.get_username())
        return self._stream_response(
            request, season, day, {stream_block(event): [error]} if error else {}
        )

    @require_POST_m
    @staff_required
    @season_view
    def slot_stream(self, request, season, day, slot_key, status, **kwargs):
        self._check_status(status)
        require(can_stream(request.user, season))
        slot = queries.slot_for(season, day, slot_key)
        if slot is None:
            raise Http404("No such slot.")
        ground_ids = streams.streamed_ground_ids(season)
        errors = {}
        for match in slot.matches:
            if streams.streamable(match, ground_ids):
                error = streams.transition(match, status, request.user.get_username())
                if error:
                    errors.setdefault(stream_block(match), []).append(error)
        return self._stream_response(request, season, day, errors)

    # --- booth ------------------------------------------------------

    def booth_context(self, request, season, ground):
        now = timezone.now()
        day = ground.local_date(now)
        previous, current, following = queries.ground_day(ground, day, now)
        # The lamp and the arm follow only the matches opted into streaming,
        # as the strip does; the runsheet itself lists every match.
        ground_ids = self._booth_ground_ids(ground)
        streamed = [
            m
            for m in queries.ground_runsheet(ground, day)
            if streams.opted_in(m, ground_ids)
        ]
        # The lamp follows the match actually on air, which can be one that
        # has overrun into the next kick-off; the strip follows the schedule.
        broadcast = next(
            (
                m
                for m in reversed(streamed)
                if streams.effective_status(m.live_stream_status) == "live"
            ),
            current,
        )
        status = (
            streams.effective_status(broadcast.live_stream_status)
            if broadcast
            else None
        )
        armable_match = self._armable_match(streamed, broadcast, now)
        armable, reason = True, ""
        if status == "live":
            armable, reason = False, "End the current broadcast first."
        elif armable_match is None:
            armable, reason = False, f"No more broadcasts on {ground.title} today."
        elif not armable_match.external_identifier:
            armable, reason = (
                False,
                f"{self._teams(armable_match)} has no YouTube broadcast.",
            )
        elif streams.effective_status(armable_match.live_stream_status) == "testing":
            armable, reason = False, "Already armed."
        return {
            "season": season,
            "ground": ground,
            "day": day,
            "daystr": day.strftime("%Y%m%d"),
            "now": now,
            "previous": previous,
            "current": current,
            "broadcast": broadcast,
            "next": following,
            "armable_match": armable_match,
            "status": status,
            "armable": armable,
            "arm_reason": reason,
            "can_stream": True,
            "panes": PANE_LABELS,
            "tzinfo": ground.get_tzinfo(),
            "user": request.user,
            "errors": [],
        }

    @staticmethod
    def _booth_ground_ids(ground):
        """The booth's ground, as a set of streamed ground ids for ``streams``."""
        return {ground.pk} if ground.live_stream else set()

    @staticmethod
    def _teams(match):
        return f"{match.get_home_team_plain()} v {match.get_away_team_plain()}"

    @staticmethod
    def _armable_match(streamed, broadcast, now):
        """
        The match the booth arms next, from the ground's matches opted into
        streaming (``streamed``, in kick-off order), so one that is not never
        holds the booth up: the first from the broadcast on air onwards
        (kicking off after ``now`` when nothing is on) that is neither live
        nor complete. The broadcast itself qualifies when it has a YouTube
        broadcast that has not gone live, as once the overrunning match before
        it has been ended. A match already testing is returned too, so the
        booth says it is armed rather than arming the match after it.
        """
        if broadcast is not None:
            position = next(
                (i for i, m in enumerate(streamed) if m.pk == broadcast.pk),
                len(streamed),
            )
            candidates = streamed[position + 1 :]
            if broadcast.external_identifier:
                candidates.insert(0, broadcast)
        else:
            candidates = [m for m in streamed if m.datetime > now]
        return next(
            (
                m
                for m in candidates
                if streams.effective_status(m.live_stream_status)
                not in ("live", "complete")
            ),
            None,
        )

    def _booth_match(self, ground, day, match_pk):
        return get_object_or_404(queries.ground_runsheet(ground, day), pk=match_pk)

    def _booth_fragments(self, request, season, ground, names):
        context = self.booth_context(request, season, ground)
        return [render_fragment(request, name, **context) for name in names]

    def _booth_refused(self, request, season, ground, context, errors):
        """
        Answer a refused booth action: the lamp alone, with the reasons, held
        and sent whole (see ``lamp`` in booth.html). A refusal changes
        nothing, so the lamp comes from the ``context`` the action checked.
        Datastar discards the body of a non-200 response, so the answer is
        200 with the reasons in the lamp.
        """
        return patches(
            request,
            lambda: [render_fragment(request, "lamp", **{**context, "errors": errors})],
            redirect_to=self._booth_url(season, ground),
            page=lambda: self.booth_page(request, season, ground, errors=errors),
            mode=ElementPatchMode.REPLACE,
        )

    def _booth_changed(self, request, season, ground):
        """
        Answer a booth action that went through: the lamp and the strip,
        re-rendered. The lamp carries no mark, which releases a held one.
        """
        return patches(
            request,
            lambda: self._booth_fragments(request, season, ground, ("lamp", "strip")),
            redirect_to=self._booth_url(season, ground),
        )

    def _booth_url(self, season, ground):
        return reverse(
            "compops:booth",
            kwargs={
                "competition": season.competition.slug,
                "season": season.slug,
                "ground": ground.slug,
            },
        )

    @login_required_m
    @season_view
    def booth_index(self, request, season, day, **kwargs):
        require(can_stream(request.user, season))
        grounds = Ground.objects.filter(
            venue__season=season, live_stream=True
        ).order_by("venue__order", "order")
        return self.render(
            request,
            self.template_path("booth_index.html"),
            {"season": season, "grounds": grounds},
        )

    @booth_view
    @booth_required
    def booth(self, request, season, ground, **kwargs):
        return self.booth_page(request, season, ground)

    def booth_page(self, request, season, ground, **overrides):
        """The whole booth page, as a plain browser gets it."""
        context = self.booth_context(request, season, ground)
        context.update(overrides)
        # The panes open on the match on air, which can have overrun into the
        # next kick-off, before the match the schedule says is on.
        match = context["broadcast"] or context["current"]
        if match:
            context["pane"] = "sheets"
            context["pane_match"] = match
            context["pane_html"] = self._pane_html(request, context, "sheets", match)
        return self.render(request, self.template_path("booth.html"), context)

    @booth_view
    @booth_required
    def booth_lamp(self, request, season, ground, **kwargs):
        (html,) = self._booth_fragments(request, season, ground, ("lamp",))
        return fragment_response(request, html)

    @booth_view
    @booth_required
    def booth_strip(self, request, season, ground, **kwargs):
        (html,) = self._booth_fragments(request, season, ground, ("strip",))
        return fragment_response(request, html)

    @require_POST_m
    @booth_view
    @booth_required
    def booth_onair(self, request, season, ground, status, **kwargs):
        if status not in ("live", "complete"):
            raise Http404("Unknown broadcast status.")
        context = self.booth_context(request, season, ground)
        errors = []
        broadcast = context["broadcast"]
        if broadcast is None:
            errors.append("Nothing is on this ground right now.")
        elif not streams.opted_in(broadcast, self._booth_ground_ids(ground)):
            # The lamp follows opted-in matches only; a guard all the same.
            errors.append(f"{self._teams(broadcast)} is not streamed.")
        elif not broadcast.external_identifier:
            errors.append(f"{self._teams(broadcast)} has no YouTube broadcast.")
        else:
            error = streams.transition(broadcast, status, request.user.get_username())
            if error:
                errors.append(error)
        if errors:
            return self._booth_refused(request, season, ground, context, errors)
        return self._booth_changed(request, season, ground)

    @require_POST_m
    @booth_view
    @booth_required
    def booth_arm(self, request, season, ground, **kwargs):
        context = self.booth_context(request, season, ground)
        if not context["armable"]:
            return self._booth_refused(
                request, season, ground, context, [context["arm_reason"]]
            )
        error = streams.transition(
            context["armable_match"], "testing", request.user.get_username()
        )
        if error:
            return self._booth_refused(request, season, ground, context, [error])
        return self._booth_changed(request, season, ground)

    def _pane_html(self, request, context, pane, match):
        extra = {"pane": pane, "pane_match": match}
        if pane == "sheets":
            extra["rosters"] = [
                (
                    team,
                    team.people.filter(is_player=True)
                    .with_statistics(team)
                    .select_related("person")
                    .order_by("number"),
                )
                for team in (match.home_team, match.away_team)
            ]
        elif pane == "results":
            extra["results"] = [
                (team, queries.team_results(team))
                for team in (match.home_team, match.away_team)
            ]
        elif pane == "ladder":
            owner = match.stage_group or match.stage
            extra["ladder"] = owner.ladder_summary.select_related("team__club")
            extra["ladder_title"] = f"{match.stage.division.title} · {owner.title}"
        elif pane == "leaders":
            extra["scorers"], extra["mvps"] = queries.division_leaders(
                match.stage.division
            )
            extra["on_field"] = {match.home_team_id, match.away_team_id}
        return render_fragment(request, f"pane_{pane}", **{**context, **extra})

    @booth_view
    @booth_required
    def booth_pane(self, request, season, ground, match_pk, pane, **kwargs):
        if pane not in PANES:
            raise Http404("No such pane.")
        context = self.booth_context(request, season, ground)
        match = self._booth_match(ground, context["day"], match_pk)
        html = self._pane_html(request, context, pane, match)
        if not request.datastar:
            return HttpResponse(html)
        return patches(request, [html], signals={"pane": pane, "match": match.pk})

    async def booth_ground(self, season, slug):
        ground = await (
            Ground.objects.filter(venue__season=season, slug=slug, live_stream=True)
            .select_related("venue")
            .order_by("venue__order", "order")
            .afirst()
        )
        if ground is None:
            raise Http404("No such streamed ground.")
        return ground

    def _booth_pane_fragment(self, request, context, pane, match_pk):
        if pane == "runsheet":
            return render_fragment(
                request,
                "pane_runsheet",
                runsheet=queries.ground_runsheet(context["ground"], context["day"]),
                **context,
            )
        # The pane and match come from the client's signals, so a stale or
        # mangled value simply has no pane to show.
        if pane in PANES and str(match_pk).isdigit():
            match = (
                queries.ground_runsheet(context["ground"], context["day"])
                .filter(pk=match_pk)
                .first()
            )
            if match is not None:
                return self._pane_html(request, context, pane, match)
        return None

    def booth_snapshot(self, request, season, ground, pane, match_pk):
        context = self.booth_context(request, season, ground)
        fragments = [
            # The stream sends the snapshot on every reconnect, so it leaves a
            # lamp that shows a refusal as it is; see lamp in booth.html.
            render_fragment(request, "lamp", keep_held=True, **context),
            render_fragment(request, "strip", **context),
        ]
        pane_html = self._booth_pane_fragment(request, context, pane, match_pk)
        if pane_html:
            fragments.append(pane_html)
        return fragments

    def booth_event_fragments(self, request, season, ground, pane, match_pk, event):
        kind = event.get("type")
        context = self.booth_context(request, season, ground)
        fragments = []
        refresh_pane = False
        if kind == "stream-changed":
            # A push about this ground releases a held lamp; one about another
            # ground leaves it as it is. See lamp in booth.html.
            keep_held = event.get("ground") != ground.pk
            fragments.append(
                render_fragment(request, "lamp", keep_held=keep_held, **context)
            )
            fragments.append(render_fragment(request, "strip", **context))
            refresh_pane = pane == "runsheet"
        elif kind in ("score-entered", "bye-processed"):
            fragments.append(render_fragment(request, "strip", **context))
            refresh_pane = pane in ("results", "ladder", "runsheet")
        elif kind == "statistics-entered":
            refresh_pane = pane in ("sheets", "leaders")
        if refresh_pane:
            pane_html = self._booth_pane_fragment(request, context, pane, match_pk)
            if pane_html:
                fragments.append(pane_html)
        return fragments

    @booth_view
    @booth_required
    def booth_runsheet(self, request, season, ground, **kwargs):
        context = self.booth_context(request, season, ground)
        html = render_fragment(
            request,
            "pane_runsheet",
            runsheet=queries.ground_runsheet(ground, context["day"]),
            **context,
        )
        if not request.datastar:
            return HttpResponse(html)
        return patches(request, [html], signals={"pane": "runsheet", "match": None})

    @booth_view
    @booth_required
    def booth_teams(self, request, season, ground, match_pk, **kwargs):
        context = self.booth_context(request, season, ground)
        match = self._booth_match(ground, context["day"], match_pk)
        division = match.stage.division
        teams = (
            Team.objects.filter(division=division)
            .select_related("stage_group")
            .order_by("stage_group__order", "order")
        )
        pools = {}
        for team in teams:
            pools.setdefault(
                team.stage_group.title if team.stage_group else "", []
            ).append(team)
        html = render_fragment(
            request,
            "teams_modal",
            division=division,
            pools=pools,
            on_field={match.home_team_id, match.away_team_id},
            **context,
        )
        if not request.datastar:
            return HttpResponse(html)
        return patches(request, [html], signals={"modal": True})

    @booth_view
    @booth_required
    def booth_team(self, request, season, ground, team_pk, **kwargs):
        context = self.booth_context(request, season, ground)
        team = get_object_or_404(
            Team.objects.select_related("division", "stage_group", "club"),
            pk=team_pk,
            division__season=season,
        )
        html = render_fragment(
            request,
            "team_modal",
            team=team,
            squad=team.people.filter(is_player=True)
            .with_statistics(team)
            .select_related("person")
            .order_by("number"),
            results=queries.team_results(team),
            **context,
        )
        if not request.datastar:
            return HttpResponse(html)
        return patches(request, [html], signals={"modal": True})
