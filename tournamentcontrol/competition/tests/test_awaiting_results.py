"""
One definition of "a match waiting for a result", shared by everything that
counts them: the dashboard's Awaiting Scores widget, ``awaiting_results`` (the
season's set-up checklist), the home page's "Enter results" task and the admin
MCP tool ``list_matches_awaiting_results``.

A match waits for a result when it has kicked off with no score, in a season
not yet complete, counts towards the ladder, is not a washout and is not
mirrored from an upstream provider. A bye waits for processing once its season
has played a match on its day or later; a processed bye never waits.
"""

import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from guardian.shortcuts import assign_perm
from test_plus import TestCase

from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition import mcp
from tournamentcontrol.competition.admin import awaiting_results
from tournamentcontrol.competition.dashboard import (
    BasicResultWidget,
    matches_require_basic_results,
)
from tournamentcontrol.competition.mcp import admin as mcp_admin
from tournamentcontrol.competition.models import Match
from tournamentcontrol.competition.tests import factories

# Build the servers before freezegun replaces ``datetime.date`` (see
# test_mcp_integration for why).
mcp.get_server()
mcp_admin.get_admin_server()

SYDNEY = "Australia/Sydney"
LOS_ANGELES = "America/Los_Angeles"
AUCKLAND = "Pacific/Auckland"

# Saturday 24 October 2026, 13:00 in Sydney and Friday 23 October, 19:00 in
# Los Angeles. The server's clock (settings.TIME_ZONE) is UTC.
NOW = "2026-10-24 02:00:00"

ICON = (
    '<svg class="wb-icon" aria-hidden="true" focusable="false">'
    '<use href="/static/touchtechnology/admin/workbook/icons.svg#%s"></use></svg>'
)


def kick_off(stage, day, at, **kwargs):
    """A match of ``stage`` on ``day`` at ``at``, in its season's time zone."""
    tzinfo = stage.division.season.get_tzinfo()
    return factories.MatchFactory.create(
        stage=stage,
        date=day,
        time=at,
        datetime=timezone.make_aware(datetime.datetime.combine(day, at), tzinfo),
        **kwargs,
    )


def bye(stage, day, **kwargs):
    """A bye of ``stage`` on ``day``, with no time or ground, as a draw makes it."""
    kwargs.setdefault("datetime", None)
    kwargs.setdefault("time", None)
    return factories.MatchFactory.create(
        stage=stage, date=day, is_bye=True, away_team=None, **kwargs
    )


def season_stage(tzname, **kwargs):
    return factories.StageFactory.create(
        division__season__timezone=tzname,
        division__season__title=kwargs.pop("title", tzname),
        **kwargs,
    )


class AwaitingResultsMixin:
    """
    Assertions that every counter of matches waiting for a result names the
    same matches.
    """

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def mcp_tool(self, **kwargs):
        toolset = mcp_admin.AdminToolset(request=SimpleNamespace(user=self.superuser))
        return toolset.list_matches_awaiting_results(**kwargs)

    def assertAwaiting(self, expected, seasons=()):
        """
        ``expected`` are the matches waiting for a result, everywhere; each of
        ``seasons`` is checked on its own too.
        """
        with self.subTest("dashboard widget"):
            self.assertCountEqual(
                BasicResultWidget()._get_context()["matches"], expected
            )
        with self.subTest("matches_require_basic_results"):
            self.assertCountEqual(matches_require_basic_results(), expected)
        with self.subTest("awaiting_results"):
            self.assertCountEqual(awaiting_results(Match.objects.all()), expected)
        with self.subTest("mcp list_matches_awaiting_results"):
            res = self.mcp_tool()
            self.assertCountEqual(
                [match["id"] for match in res["matches"]],
                [match.pk for match in expected],
            )
            self.assertEqual(res["total"], len(expected))
        for season in seasons:
            mine = [m for m in expected if m.stage.division.season_id == season.pk]
            with self.subTest("awaiting_results", season=season.title):
                self.assertCountEqual(awaiting_results(season.matches), mine)
            with self.subTest("mcp list_matches_awaiting_results", season=season.title):
                self.assertEqual(self.mcp_tool(season_id=season.pk)["total"], len(mine))


@freeze_time(NOW)
class AwaitingResultsTests(AwaitingResultsMixin, TestCase):
    """
    A season in Sydney that has played three Saturdays of four, with every kind
    of match on them, beside a season in Los Angeles whose third Saturday has
    not yet come and a season that is complete.
    """

    def setUp(self):
        super().setUp()
        evening = datetime.time(18, 0)
        morning = datetime.time(10, 0)
        afternoon = datetime.time(15, 0)  # 04:00 UTC, still to come

        stage = season_stage(SYDNEY, title="Spring 2026")
        self.sydney = stage.division.season
        oct10, oct17, oct24, oct31 = (
            datetime.date(2026, 10, day) for day in (10, 17, 24, 31)
        )
        # Saturday 10 October: a result, and a processed bye.
        kick_off(stage, oct10, evening, home_team_score=5, away_team_score=3)
        self.processed_bye = bye(stage, oct10, bye_processed=True)
        # Saturday 17 October: a result, a match with none, a bye not yet
        # processed, a washout, a match the ladder leaves out and a match
        # mirrored from an upstream provider (its result comes from there).
        kick_off(stage, oct17, evening, home_team_score=2, away_team_score=2)
        self.no_score = kick_off(stage, oct17, evening)
        self.unprocessed_bye = bye(stage, oct17)
        kick_off(stage, oct17, evening, is_washout=True)
        kick_off(stage, oct17, evening, include_in_ladder=False)
        kick_off(stage, oct17, evening, upstream_id="mysideline:12345")
        # Saturday 24 October, today: the morning has been played, the
        # afternoon is to come. One bye is processed (one given a kick-off
        # time), one is not.
        kick_off(stage, oct24, morning, home_team_score=4, away_team_score=1)
        kick_off(stage, oct24, afternoon)
        self.timed_processed_bye = bye(
            stage,
            oct24,
            bye_processed=True,
            time=morning,
            datetime=timezone.make_aware(
                datetime.datetime.combine(oct24, morning), ZoneInfo(SYDNEY)
            ),
        )
        self.todays_bye = bye(stage, oct24)
        # Saturday 31 October: still to come.
        kick_off(stage, oct31, evening)
        bye(stage, oct31)

        # Los Angeles: Saturday 17 October is played and its bye processed;
        # Saturday 24 October has not come there yet (it is Friday evening),
        # even though it has in Sydney and on the server's clock.
        stage = season_stage(LOS_ANGELES, title="Pacific 2026")
        self.los_angeles = stage.division.season
        kick_off(stage, oct17, morning, home_team_score=1, away_team_score=0)
        bye(stage, oct17, bye_processed=True)
        self.la_match = kick_off(stage, oct24, morning)
        self.la_bye = bye(stage, oct24)

        # A complete season: nothing in it waits, whatever is missing.
        stage = season_stage(SYDNEY, title="Autumn 2026")
        self.autumn = stage.division.season
        self.autumn.complete = True
        self.autumn.save()
        kick_off(stage, datetime.date(2026, 4, 11), evening)
        bye(stage, datetime.date(2026, 4, 11))

    def test_every_counter_agrees(self):
        self.assertAwaiting(
            [self.no_score, self.unprocessed_bye, self.todays_bye],
            seasons=[self.sydney, self.los_angeles, self.autumn],
        )

    def test_a_processed_bye_never_waits(self):
        waiting = matches_require_basic_results()
        for match in (self.processed_bye, self.timed_processed_bye):
            with self.subTest(match=match.pk):
                self.assertEqual(waiting.filter(pk=match.pk).exists(), False)
                self.assertEqual(
                    awaiting_results(self.sydney.matches).filter(pk=match.pk).exists(),
                    False,
                )

    def test_a_bye_waits_once_its_own_season_has_played_its_day(self):
        # Sydney has played Saturday 24 October; Los Angeles has not, so its
        # bye that day does not wait yet.
        self.assertEqual(awaiting_results(self.los_angeles.matches).count(), 0)
        with freeze_time("2026-10-24 17:00:00"):  # 10:00 in Los Angeles
            self.assertCountEqual(
                awaiting_results(self.los_angeles.matches),
                [self.la_match, self.la_bye],
            )
            self.assertEqual(
                matches_require_basic_results().filter(pk=self.la_bye.pk).exists(),
                True,
            )


@per_shell(shells=("workbook",))
@freeze_time(NOW)
class HomePageTests(AwaitingResultsMixin, TestCase):
    """The home page's task and widget name the same day as the rest."""

    def setUp(self):
        super().setUp()
        stage = season_stage(SYDNEY, title="Spring 2026")
        self.season = stage.division.season
        oct17, oct24 = datetime.date(2026, 10, 17), datetime.date(2026, 10, 24)
        self.no_score = kick_off(stage, oct17, datetime.time(18, 0))
        kick_off(
            stage, oct24, datetime.time(10, 0), home_team_score=4, away_team_score=1
        )
        # Processed byes on the latest day played: done, so not the task's day.
        bye(stage, oct24, bye_processed=True)
        bye(stage, oct24, bye_processed=True)

    def test_the_task_and_the_widget_name_the_day_waiting(self):
        self.assertAwaiting([self.no_score], seasons=[self.season])
        with self.login(self.superuser):
            self.get_check_200("admin:index")
        url = reverse(
            "admin:fixja:match-results",
            args=(self.season.competition_id, self.season.pk, "20261017"),
        )
        self.assertResponseContains(
            f'<a class="wb-task" href="{url}">'
            f'<span class="wb-task-icon">{ICON % "list-checks"}</span>'
            '<span class="wb-task-title">Enter results</span>'
            '<span class="wb-task-note">Sat 17 Oct · Spring 2026</span></a>',
        )
        day = {
            "competition_id": self.season.competition_id,
            "season_id": self.season.pk,
            "datestr": "20261017",
        }
        day_url = reverse("admin:competition:match-results", kwargs=day)
        time_url = reverse(
            "admin:competition:match-results", kwargs=dict(day, timestr="1800")
        )
        self.assertResponseContains(
            f'<li><a class="wb-widget-date" href="{day_url}">Sat 17 Oct 2026</a>'
            f'<a class="wb-badge" href="{time_url}">18:00</a></li>',
        )

    def test_nothing_waiting_when_the_only_byes_are_processed(self):
        self.no_score.home_team_score = 3
        self.no_score.away_team_score = 3
        self.no_score.save()
        self.assertAwaiting([], seasons=[self.season])
        with self.login(self.superuser):
            self.get_check_200("admin:index")
        self.assertResponseContains(
            '<li class="wb-muted">'
            f'{ICON % "circle-check"} No matches awaiting result entry.</li>',
        )
        self.assertResponseNotContains(
            '<span class="wb-task-title">Enter results</span>'
        )


class TimeZoneTests(AwaitingResultsMixin, TestCase):
    """
    "Today" is the season's day, not the server's: a bye waits once its season
    has kicked off a match on its day or later, wherever the season is.
    """

    def test_a_season_behind_the_server(self):
        stage = season_stage(LOS_ANGELES)
        played = datetime.date(2026, 10, 17)
        saturday = datetime.date(2026, 10, 24)
        kick_off(
            stage, played, datetime.time(10, 0), home_team_score=1, away_team_score=0
        )
        kick_off(
            stage, saturday, datetime.time(10, 0), home_team_score=2, away_team_score=0
        )
        waiting = bye(stage, saturday)
        # Saturday on the server, Friday evening in Los Angeles.
        with freeze_time("2026-10-24 02:00:00"):
            self.assertAwaiting([], seasons=[stage.division.season])
        # Saturday 10:00 in Los Angeles: the first match has kicked off.
        with freeze_time("2026-10-24 17:00:00"):
            self.assertAwaiting([waiting], seasons=[stage.division.season])

    def test_a_season_ahead_of_the_server(self):
        stage = season_stage(AUCKLAND)
        saturday = datetime.date(2026, 10, 24)
        kick_off(
            stage, saturday, datetime.time(10, 0), home_team_score=1, away_team_score=0
        )
        waiting = bye(stage, saturday)
        # Saturday 09:00 in Auckland, Friday on the server.
        with freeze_time("2026-10-23 20:00:00"):
            self.assertAwaiting([], seasons=[stage.division.season])
        # Saturday 10:30 in Auckland, still Friday on the server.
        with freeze_time("2026-10-23 21:30:00"):
            self.assertAwaiting([waiting], seasons=[stage.division.season])


@freeze_time(NOW)
@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class PublicResultsPageTests(AwaitingResultsMixin, TestCase):
    """
    The public site's result entry page lists the kick-off times waiting for a
    result. A superuser also sees the year ahead, so results can be entered
    early.
    """

    def setUp(self):
        super().setUp()
        stage = season_stage(SYDNEY, title="Spring 2026")
        self.season = stage.division.season
        kick_off(stage, datetime.date(2026, 10, 17), datetime.time(18, 0))
        kick_off(stage, datetime.date(2026, 10, 31), datetime.time(19, 0))
        self.scorer = UserFactory.create()
        assign_perm("competition.change_match", self.scorer)

    def time_html(self, datestr, timestr, label):
        url = reverse(
            "competition:match-results",
            kwargs={
                "competition": self.season.competition.slug,
                "season": self.season.slug,
                "datestr": datestr,
                "timestr": timestr,
            },
        )
        return f'<li><a href="{url}">{label}</a></li>'

    def test_a_scorer_sees_the_matches_played_a_superuser_the_year_ahead(self):
        with self.login(self.scorer):
            self.get_check_200(
                "competition:results", self.season.competition.slug, self.season.slug
            )
        self.assertResponseContains(self.time_html("20261017", "1800", "6 p.m."))
        self.assertResponseNotContains(self.time_html("20261031", "1900", "7 p.m."))
        with self.login(self.superuser):
            self.get_check_200(
                "competition:results", self.season.competition.slug, self.season.slug
            )
        self.assertResponseContains(self.time_html("20261017", "1800", "6 p.m."))
        self.assertResponseContains(self.time_html("20261031", "1900", "7 p.m."))
