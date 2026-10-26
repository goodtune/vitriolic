import collections
import logging

from django.db.models import Count, Exists, OuterRef, Q
from django.db.models.expressions import RawSQL
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from touchtechnology.admin.base import DashboardWidget
from tournamentcontrol.competition.models import Match, Stage, Team, UndecidedTeam
from tournamentcontrol.competition.utils import (
    legitimate_bye_match,
    team_awaits_upstream,
    team_needs_progressing,
)

logger = logging.getLogger(__name__)


def matches_require_basic_results(now=None, matches=None):
    """
    Matches waiting for a result: the one definition, shared by the Awaiting
    Scores widget, the home page's "Enter results" task, the season's set-up
    checklist and the admin MCP tool ``list_matches_awaiting_results``.

    A match waits once it has kicked off (at or before ``now``) with no score.
    A bye waits for processing once its season has kicked off a match on the
    bye's day or later: a bye has no kick-off of its own, and its season's
    matches say when its day has come where the season is played, whatever
    the server's clock says. A processed bye never waits (processing leaves
    its scores empty). Washouts, matches the ladder leaves out, matches in a
    complete season and matches mirrored from an upstream provider (their
    results come from the provider, so they are never entered here) never
    wait.

    ``matches`` narrows the matches looked at (a season's, a day's); the
    conditions above always apply to it.
    """
    if now is None:
        now = timezone.now()
        now = now.replace(second=0, microsecond=0)

    if timezone.is_naive(now):
        now = timezone.make_aware(now, timezone.get_default_timezone())

    if matches is None:
        matches = Match.objects.all()

    kicked_off = Q(is_bye=False, datetime__lte=now)
    day_played = Exists(
        Match.objects.filter(
            stage__division__season=OuterRef("stage__division__season"),
            datetime__lte=now,
            date__gte=OuterRef("date"),
        )
    )
    bye_due = Q(is_bye=True, bye_processed=False) & Q(day_played)

    return (
        matches.filter(
            kicked_off | bye_due,
            stage__division__season__complete=False,
            home_team_score=None,
            away_team_score=None,
            is_washout=False,
            include_in_ladder=True,
            upstream_id__isnull=True,
        )
        .select_related(
            "stage__division__season__competition",
            "play_at",
            "home_team__club",
            "home_team__division",
            "away_team__club",
            "away_team__division",
        )
        .defer(
            "live_stream_thumbnail_image",
            "stage__division__season__live_stream_thumbnail_image",
        )
    )


def matches_require_details_results(matches=None, include_forfeits=False):
    """
    Matches with a result in a season that records statistics but with no
    detailed result yet. Matches mirrored from an upstream provider are left
    out, as they are for basic results: their results come from the provider,
    so their detailed results are never entered here.
    """
    # If not provided up front, build a base queryset of all matches
    if matches is None:
        matches = Match.objects.filter(
            is_forfeit=False,
            stage__division__season__complete=False,
        )

    matches = matches.filter(
        stage__division__season__statistics=True,
        statistics__isnull=True,
        home_team__isnull=False,
        home_team_score__isnull=False,
        away_team__isnull=False,
        away_team_score__isnull=False,
        upstream_id__isnull=True,
    )

    if not include_forfeits:
        matches = matches.filter(is_forfeit=False)

    return matches.select_related(
        "stage__division__season__competition",
        "play_at",
        "home_team__club",
        "home_team__division",
        "away_team__club",
        "away_team__division",
    ).defer(
        "live_stream_thumbnail_image",
        "stage__division__season__live_stream_thumbnail_image",
    )


def matches_require_progression():
    """
    Matches with a team still to be decided, in a season not yet complete. A
    match mirrored from an upstream provider which has yet to name its teams
    is left out: only the provider can fill them in, on a later sync.
    """
    matches = (
        Match.objects.filter(team_needs_progressing)
        .exclude(legitimate_bye_match)
        .exclude(team_awaits_upstream)
    )
    matches = matches.order_by("stage__division", "stage")

    return matches.select_related(
        "stage__division__season__competition",
        "play_at",
        "home_team__club",
        "home_team__division",
        "away_team__club",
        "away_team__division",
    ).defer(
        "live_stream_thumbnail_image",
        "stage__division__season__live_stream_thumbnail_image",
    )


def matches_progression_possible():
    matches = matches_require_progression()

    # cache which stages have all their matches played or byes marked played,
    # and which hold a place a person can fill (an undecided team of our own:
    # the upstream sync's placeholder is not one, see
    # ``UndecidedTeamQuerySet.of_our_own``)
    stages = (
        Stage.objects.filter(matches__in=matches)
        .distinct()
        .annotate(
            has_places=Exists(
                UndecidedTeam.objects.of_our_own().filter(stage=OuterRef("pk"))
            )
        )
    )
    score_entered = Q(home_team_score__isnull=False, away_team_score__isnull=False)
    played_bye = Q(is_bye=True, bye_processed=True)
    is_washout = Q(is_washout=True)
    _stage_cache = {}
    _places_cache = {}
    for stage in stages:
        _places_cache[stage.pk] = stage.has_places
        try:
            preceding = stage.comes_after
        except Stage.DoesNotExist:
            # The first stage of its division: no stage before it can hold its
            # progression back (its winners and losers come from its own
            # matches, see ``Match.eval``).
            _stage_cache[stage.pk] = 0
        else:
            _stage_cache[stage.pk] = preceding.matches.exclude(
                score_entered | played_bye | is_washout
            ).count()

    def _can_evaluate(match):
        """
        If we can actually evaluate a Team instance for assignment into
        the `home_team` OR `away_team` field, then this is a match we
        want to know about. Not possible to do directly in a QuerySet as
        there is too much logic on the models, so we need to attempt this
        for every match that could possibly be progressed.
        """
        # If there are any unplayed or unprocessed matches in the preceding
        # stage, then we do not want to consider this match as viable for
        # progression.
        if _stage_cache[match.stage_id]:
            return False

        # If the home or away team can be determined we would want to progress
        # the match. This should only catch Px, GxPx, Wx, Lx - for
        # UndecidedTeam cases we need to catch them all together.
        home_team, away_team = match.eval(lazy=True)
        if match.home_team is None and isinstance(home_team, Team):
            return True
        elif match.away_team is None and isinstance(away_team, Team):
            return True

        # Otherwise the stage is progressed by hand, if it holds a place a
        # person can fill.
        return _places_cache[match.stage_id]

    matches = [m for m in matches if _can_evaluate(m)]

    return matches


def stages_require_progression():
    matches = matches_progression_possible()
    stages = {}
    for m in matches:
        stages.setdefault(m.stage.division, {}).setdefault(m.stage, []).append(m)
    return stages


#
# Dashboard Widgets
#


class BasicResultWidget(DashboardWidget):
    verbose_name = _("Awaiting Scores")
    template = "tournamentcontrol/competition/admin/widgets/results/basic.html"

    def _get_context(self):
        matches = matches_require_basic_results()
        matches = matches.order_by("date", "time")

        dates = matches.values_list(
            "stage__division__season__competition", "stage__division__season", "date"
        ).distinct()
        times = matches.values_list(
            "stage__division__season__competition",
            "stage__division__season",
            "date",
            "time",
        ).distinct()

        # Construct an interim data structure
        data = collections.OrderedDict()
        for competition, season, date, time in times:
            key = (competition, season, date)
            data.setdefault(key, []).append(time)

        # Remove any None values from the list of times if there are any
        # real times in the list. If not, we'll keep it so our template
        # can iterate the "loop" at least once.
        dates_times = []
        for key, time_list in data.items():
            if [t for t in time_list if t] and None in time_list:
                time_list.remove(None)
            for time in time_list:
                dates_times.append(key + (time,))

        context = {"matches": matches, "dates": dates, "dates_times": dates_times}
        return context


class ProgressStageWidget(DashboardWidget):
    verbose_name = _("Progress Teams")
    template = "tournamentcontrol/competition/admin/widgets/progress/stages.html"

    def _get_context(self):
        stages = stages_require_progression()

        context = {"stages": stages}
        return context


class DetailResultWidget(DashboardWidget):
    verbose_name = _("Awaiting Detailed Results")
    template = "tournamentcontrol/competition/admin/widgets/results/detailed.html"

    @classmethod
    def show(cls):
        matches = matches_require_details_results()
        return bool(matches.count())

    @property
    def matches(self):
        if not hasattr(self, "_matches"):
            self._matches = matches_require_details_results()
        return self._matches

    def _get_context(self):
        context = {"matches": self.matches}
        return context


class MostValuableWidget(DashboardWidget):
    verbose_name = _("Awaiting MVP Points")
    template = "tournamentcontrol/competition/admin/widgets/results/detailed.html"

    @property
    def matches(self):
        """
        Matches where one team's players have statistics but their MVP
        points total less than one.

        The raw SQL only picks the matches; the rows are then fetched with
        their teams, clubs, stage, division, season and competition, which
        the template shows for each row. Fetching them from the raw query
        cost the template several queries for every row.

        The query starts from the matches in stages that keep MVP points in
        seasons this widget lists, and joins each statistic to the
        association of its player with the home or away team of its match,
        so the database can find that association by team and person rather
        than reading every team its player has ever been part of.
        """
        sql = """
            SELECT
                m.id
            FROM
                competition_season se
            JOIN
                competition_division d ON (d.season_id = se.id)
            JOIN
                competition_stage g ON (g.division_id = d.id)
            JOIN
                competition_match m ON (m.stage_id = g.id)
            JOIN
                competition_simplescorematchstatistic s ON (s.match_id = m.id)
            JOIN
                competition_teamassociation t
                ON (
                    t.person_id = s.player_id
                  AND
                    t.team_id IN (m.home_team_id, m.away_team_id)
                )
            WHERE
                  t.is_player
                AND
                  g.keep_mvp
                AND
                  (NOT se.complete OR se.mvp_results_public IS NULL)
            GROUP BY
                m.id, t.team_id
            HAVING
                SUM(s.mvp) < %s
        """
        # FIXME should not be a static value
        return (
            Match.objects.filter(pk__in=RawSQL(sql, (1,)))
            .select_related(
                "stage__division__season__competition",
                "home_team__club",
                "away_team__club",
            )
            .defer(
                "live_stream_thumbnail_image",
                "stage__division__season__live_stream_thumbnail_image",
            )
        )

    def _get_context(self):
        context = {"matches": self.matches}
        return context


class ScoresheetWidget(DashboardWidget):
    verbose_name = _("Season Reports")
    template = "tournamentcontrol/competition/admin/widgets/scoresheets.html"

    def _get_context(self):
        stages = (
            Stage.objects.annotate(p=Count("matches_needing_printing"))
            .filter(p__gt=0)
            # each row links to its division, season and competition
            .select_related("division__season__competition")
            .defer("division__season__live_stream_thumbnail_image")
        )
        context = {"stages": stages}
        return context


class ReportWidget(DashboardWidget):
    verbose_name = _("Reports")
    template = "tournamentcontrol/competition/admin/widgets/reports.html"

    def _get_context(self):
        context = {}
        return context
