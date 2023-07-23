import collections
import logging
from functools import reduce

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.functional import lazy
from django.utils.translation import gettext_lazy as _

from touchtechnology.admin.base import DashboardWidget
from tournamentcontrol.competition.models import Match, Stage, Team
from tournamentcontrol.competition.utils import legitimate_bye_match, team_needs_progressing

logger = logging.getLogger(__name__)


def matches_require_basic_results(now=None, matches=None):
    if now is None:
        now = timezone.now()
        now = now.replace(second=0, microsecond=0)

    if settings.USE_TZ and timezone.is_naive(now):
        timezone.make_aware(now, timezone.get_default_timezone())

    # If not provided up front, build a base queryset of matches that take
    # place prior to "now".
    if matches is None:
        try:
            last_bye_date = (
                Match.objects.filter(datetime__lte=now).dates("date", "day").latest()
            )
        except Match.DoesNotExist:
            last_bye_date = now.date()
        matches = Match.objects.filter(
            Q(datetime__lte=now)
            | Q(is_bye=True, bye_processed=False, date__lte=last_bye_date),
            stage__division__season__complete=False,
        )

    return matches.filter(
        home_team_score=None,
        away_team_score=None,
        is_washout=False,
    ).select_related(
        "stage__division__season__competition",
        "play_at",
        "home_team__club",
        "home_team__division",
        "away_team__club",
        "away_team__division",
    )


def matches_require_details_results(matches=None, include_forfeits=False):
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
    )


def matches_require_progression():
    matches = Match.objects.filter(team_needs_progressing).exclude(legitimate_bye_match)
    matches = matches.order_by("stage__division", "stage")

    return matches.select_related(
        "stage__division__season__competition",
        "play_at",
        "home_team__club",
        "home_team__division",
        "away_team__club",
        "away_team__division",
    )


def matches_progression_possible():
    matches = matches_require_progression()

    # cache which stages have all their matches played or byes marked played
    stages = Stage.objects.filter(matches__in=matches).distinct()
    score_entered = Q(home_team_score__isnull=False, away_team_score__isnull=False)
    played_bye = Q(is_bye=True, bye_processed=True)
    is_washout = Q(is_washout=True)
    _stage_cache = {}
    for stage in stages:
        f = stage.comes_after
        try:
            _stage_cache[stage.pk] = f.matches.exclude(
                score_entered | played_bye | is_washout
            ).count()
        except AttributeError:
            _stage_cache[stage.pk] = 0

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
        logger.debug("Evaluate %r - home_team=%s home_team_eval=%s home_team_eval_related=%s", match, match.home_team, match.home_team_eval, match.home_team_eval_related)
        logger.debug("Evaluate %r - away_team=%s away_team_eval=%s away_team_eval_related=%s", match, match.away_team, match.away_team_eval, match.away_team_eval_related)
        if _stage_cache[match.stage_id]:
            logger.warning("Can't eval %s from stage %r (%s matches)", match, match.stage, _stage_cache[match.stage_id])
            return False

        # If the home or away team can be determined we would want to progress
        # the match. This should only catch Px, GxPx, Wx, Lx - for
        # UndecidedTeam cases we need to catch them all together.
        home_team, away_team = match.eval()
        if match.home_team is None and isinstance(home_team, Team):
            return True
        elif match.away_team is None and isinstance(away_team, Team):
            return True

        if match.stage.undecided_teams.exists() and _stage_cache[match.stage_id] == 0:
            logger.warning("Found undecided teams and no matches left for %s in stage %r", match, match.stage)
            return True

        logger.warning("Can't evaluate %r - home_team=%r away_team=%r", match, home_team, away_team)
        return False

    matches = [m for m in matches if _can_evaluate(m)]

    return matches


def stages_require_progression():
    matches = matches_progression_possible()

    # Turn the list of matches with progressions into a nested OrderedDict
    # for use in the template. Use of OrderedDict means our ordering set
    # above will not be lost.
    stages = collections.OrderedDict()
    for m in matches:
        stages.setdefault(m.stage.division, collections.OrderedDict()).setdefault(
            m.stage, []
        ).append(m)

    return stages


lazy_stages_require_progression = lazy(stages_require_progression, dict)


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
        stages = lazy_stages_require_progression()

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
        sql = """
            SELECT DISTINCT
                m.id, m.home_team_id, m.away_team_id, m.stage_id, m.date,
                m.datetime, m.label, m.round
            FROM
                competition_simplescorematchstatistic s
            JOIN
                competition_teamassociation t ON (s.player_id = t.person_id)
            JOIN
                  competition_match m
                ON (
                    m.id = s.match_id
                  AND (
                      m.home_team_id = t.team_id
                    OR
                      m.away_team_id = t.team_id
                  )
                )
            JOIN
                competition_stage g ON (m.stage_id = g.id)
            JOIN
                competition_division d ON (g.division_id = d.id)
            JOIN
                competition_season se ON (d.season_id = se.id)
            WHERE
                  t.is_player
                AND
                  g.keep_mvp
                AND
                  (NOT se.complete OR se.mvp_results_public IS NULL)
            GROUP BY
                m.id, team_id, m.home_team_id, m.away_team_id, m.stage_id,
                m.date, m.datetime, m.label, m.round
            HAVING
                SUM(mvp) < %s
        """
        # FIXME should not be a static value
        return Match.objects.raw(sql, params=(1,))

    def _get_context(self):
        context = {"matches": self.matches}
        return context


class ScoresheetWidget(DashboardWidget):
    verbose_name = _("Season Reports")
    template = "tournamentcontrol/competition/admin/widgets/scoresheets.html"

    def _get_context(self):
        stages = Stage.objects.annotate(p=Count("matches_needing_printing")).filter(
            p__gt=0
        )
        context = {"stages": stages}
        return context


class ReportWidget(DashboardWidget):
    verbose_name = _("Reports")
    template = "tournamentcontrol/competition/admin/widgets/reports.html"

    def _get_context(self):
        context = {}
        return context
