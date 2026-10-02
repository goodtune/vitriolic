import collections
from datetime import date, datetime, timezone

from django.conf import settings
from django.test import override_settings
from test_plus import TestCase

from tournamentcontrol.competition.checks import (
    HTMX_MIDDLEWARE,
    check_htmx_middleware,
)
from tournamentcontrol.competition.models import Match
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.utils import matches_timeline


class HtmxMiddlewareCheckTests(TestCase):
    """
    The competition views rely on request.htmx, so the django-htmx
    middleware is a hard requirement enforced by a system check.
    """

    def test_check_passes_with_middleware(self):
        self.assertEqual(check_htmx_middleware(None), [])

    def test_check_fails_without_middleware(self):
        MIDDLEWARE = [m for m in settings.MIDDLEWARE if m != HTMX_MIDDLEWARE]
        with override_settings(MIDDLEWARE=MIDDLEWARE):
            self.assertEqual(
                [error.id for error in check_htmx_middleware(None)],
                ["tournamentcontrol.competition.E001"],
            )


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class DisabledExperimentalViewTests(TestCase):
    """
    Seasons that have not opted in must behave exactly as before — the
    experimental views return Not Found.
    """

    def test_season_fixtures_not_enabled(self):
        season = factories.SeasonFactory.create()
        self.get(
            "competition:season-fixtures", season.competition.slug, season.slug
        )
        self.response_404()

    def test_team_timeline_not_enabled(self):
        team = factories.TeamFactory.create()
        season = team.division.season
        self.get(
            "competition:team-timeline",
            season.competition.slug,
            season.slug,
            team.division.slug,
            team.slug,
        )
        self.response_404()


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class SeasonFixturesTests(TestCase):
    def setUp(self):
        self.season = factories.SeasonFactory.create(enable_experimental_views=True)

    def test_season_fixtures(self):
        stage = factories.StageFactory.create(division__season=self.season)
        factories.MatchFactory.create_batch(
            5,
            stage=stage,
            date="2022-07-02",
            time="09:00",
            datetime="2022-07-02 09:00",
        )
        self.assertGoodView(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
        )
        self.assertEqual(self.get_context("match_count"), 5)

        # the page shell carries a day index without materialising any
        # match rows — each day's table is fetched separately
        self.assertEqual(
            self.get_context("day_index"),
            [{"date": date(2022, 7, 2), "count": 5}],
        )
        self.assertIsNone(self.get_context("day_matches"))
        self.assertResponseContains(
            '<a href="?day=2022-07-02">Show 5 matches</a>'
        )

    def test_season_fixtures_day(self):
        stage = factories.StageFactory.create(division__season=self.season)
        matches = factories.MatchFactory.create_batch(
            5,
            stage=stage,
            date="2022-07-02",
            time="09:00",
            datetime="2022-07-02 09:00",
        )
        factories.MatchFactory.create(
            stage=stage,
            date="2022-07-03",
            time="09:00",
            datetime="2022-07-03 09:00",
        )
        self.assertGoodView(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
            data={"day": "2022-07-02"},
        )
        day_matches = self.get_context("day_matches")
        self.assertCountEqual(day_matches, matches)

        # the live-stream thumbnail blob must never be dragged out of the
        # database for a listing — hundreds of matches each carrying an
        # image is hundreds of megabytes per request at tournament scale
        self.assertIn(
            "live_stream_thumbnail_image", day_matches[0].get_deferred_fields()
        )

    def test_season_fixtures_day_htmx_fragment(self):
        stage = factories.StageFactory.create(division__season=self.season)
        factories.MatchFactory.create(
            stage=stage,
            date="2022-07-02",
            time="09:00",
            datetime="2022-07-02 09:00",
        )
        self.get(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
            data={"day": "2022-07-02"},
            extra={"HTTP_HX_REQUEST": "true"},
        )
        self.response_200()
        self.assertTemplateUsed(
            self.last_response,
            "tournamentcontrol/competition/_season_fixtures_day.html",
        )
        self.assertTemplateNotUsed(
            self.last_response,
            "tournamentcontrol/competition/season_fixtures.html",
        )

    def test_season_fixtures_day_invalid(self):
        self.get(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
            data={"day": "not-a-day"},
        )
        self.response_404()

    def test_season_fixtures_excludes_unscheduled_matches(self):
        stage = factories.StageFactory.create(division__season=self.season)
        factories.MatchFactory.create(
            stage=stage,
            date="2022-07-02",
            time="09:00",
            datetime="2022-07-02 09:00",
        )
        factories.MatchFactory.create(stage=stage, date=None)
        self.assertGoodView(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
        )
        self.assertEqual(self.get_context("match_count"), 1)
        self.assertEqual(
            self.get_context("day_index"),
            [{"date": date(2022, 7, 2), "count": 1}],
        )

    def test_season_fixtures_day_outside_selection(self):
        stage = factories.StageFactory.create(division__season=self.season)
        factories.MatchFactory.create(
            stage=stage,
            date="2022-07-02",
            time="09:00",
            datetime="2022-07-02 09:00",
        )
        self.get(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
            data={"day": "2022-07-09"},
        )
        self.response_404()

    def test_season_fixtures_division_filter(self):
        stage1 = factories.StageFactory.create(division__season=self.season)
        stage2 = factories.StageFactory.create(division__season=self.season)
        factories.MatchFactory.create_batch(
            3,
            stage=stage1,
            date="2022-07-02",
            time="09:00",
            datetime="2022-07-02 09:00",
        )
        factories.MatchFactory.create_batch(
            2,
            stage=stage2,
            date="2022-07-02",
            time="10:00",
            datetime="2022-07-02 10:00",
        )
        self.assertGoodView(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
            data={"division": stage1.division.slug},
        )
        self.assertEqual(self.get_context("match_count"), 3)

    def test_season_fixtures_team_filter(self):
        stage = factories.StageFactory.create(division__season=self.season)
        team = factories.TeamFactory.create(division=stage.division)
        factories.MatchFactory.create(
            stage=stage,
            home_team=team,
            date="2022-07-02",
            time="09:00",
            datetime="2022-07-02 09:00",
        )
        factories.MatchFactory.create(
            stage=stage,
            date="2022-07-02",
            time="10:00",
            datetime="2022-07-02 10:00",
        )
        self.assertGoodView(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
            data={"team": team.slug},
        )
        self.assertEqual(self.get_context("match_count"), 1)

    def test_season_fixtures_team_filter_unknown(self):
        self.get(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
            data={"team": "no-such-team"},
        )
        self.response_404()

    def test_season_fixtures_place_filter(self):
        stage = factories.StageFactory.create(division__season=self.season)
        venue = factories.VenueFactory.create(season=self.season)
        ground1 = factories.GroundFactory.create(venue=venue)
        ground2 = factories.GroundFactory.create(venue=venue)
        factories.MatchFactory.create(
            stage=stage,
            play_at=ground1,
            date="2022-07-02",
            time="09:00",
            datetime="2022-07-02 09:00",
        )
        factories.MatchFactory.create(
            stage=stage,
            play_at=ground2,
            date="2022-07-02",
            time="10:00",
            datetime="2022-07-02 10:00",
        )

        # a single ground only shows matches on that ground
        self.assertGoodView(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
            data={"place": ground1.pk},
        )
        self.assertEqual(self.get_context("match_count"), 1)

        # the venue includes matches on all of its grounds
        self.assertGoodView(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
            data={"place": venue.pk},
        )
        self.assertEqual(self.get_context("match_count"), 2)

    def test_season_fixtures_place_filter_unknown(self):
        self.get(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
            data={"place": "0"},
        )
        self.response_404()
        self.get(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
            data={"place": "not-a-pk"},
        )
        self.response_404()

    def test_season_fixtures_excludes_draft_divisions(self):
        stage = factories.StageFactory.create(division__season=self.season)
        draft_stage = factories.StageFactory.create(
            division__season=self.season, division__draft=True
        )
        factories.MatchFactory.create(
            stage=stage,
            date="2022-07-02",
            time="09:00",
            datetime="2022-07-02 09:00",
        )
        factories.MatchFactory.create(
            stage=draft_stage,
            date="2022-07-02",
            time="10:00",
            datetime="2022-07-02 10:00",
        )
        self.assertGoodView(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
        )
        self.assertEqual(self.get_context("match_count"), 1)
        self.assertCountEqual(
            self.get_context("divisions"), [stage.division]
        )

        # a draft division is not a valid filter value either
        self.get(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
            data={"division": draft_stage.division.slug},
        )
        self.response_404()

    def test_season_fixtures_excludes_byes(self):
        stage = factories.StageFactory.create(division__season=self.season)
        factories.MatchFactory.create(
            stage=stage,
            date="2022-07-02",
            time="09:00",
            datetime="2022-07-02 09:00",
        )
        factories.MatchFactory.create(
            stage=stage,
            away_team=None,
            is_bye=True,
            date="2022-07-02",
        )
        self.assertGoodView(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
        )
        self.assertEqual(self.get_context("match_count"), 1)


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class TeamTimelineTests(TestCase):
    def setUp(self):
        self.season = factories.SeasonFactory.create(enable_experimental_views=True)
        self.stage = factories.StageFactory.create(division__season=self.season)
        self.team = factories.TeamFactory.create(division=self.stage.division)

    def assertGoodTimeline(self):
        self.assertGoodView(
            "competition:team-timeline",
            self.season.competition.slug,
            self.season.slug,
            self.team.division.slug,
            self.team.slug,
        )

    def test_team_timeline(self):
        factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.team,
            date="2022-07-02",
            time="09:00",
            datetime="2022-07-02 09:00",
            home_team_score=5,
            away_team_score=3,
        )
        factories.MatchFactory.create(
            stage=self.stage,
            away_team=self.team,
            date="2022-07-02",
            time="12:00",
            datetime="2022-07-02 12:00",
        )
        self.assertGoodTimeline()

        timeline = self.get_context("timeline")
        self.assertEqual(len(timeline), 1)
        items = timeline[0]["items"]
        self.assertEqual(len(items), 2)

        # first match of the day carries no rest gap, the second reports
        # the time since the earlier start
        self.assertIsNone(items[0]["gap"])
        self.assertEqual(str(items[1]["gap_display"]), "3h")

        # thumbnail blobs stay in the database for timeline listings too
        self.assertIn(
            "live_stream_thumbnail_image",
            items[0]["match"].get_deferred_fields(),
        )

        # the played match is not "next", the unplayed one is
        self.assertEqual(items[0]["is_next"], False)
        self.assertEqual(items[1]["is_next"], True)

    def test_team_timeline_record(self):
        factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.team,
            date="2022-07-02",
            time="09:00",
            datetime="2022-07-02 09:00",
            home_team_score=5,
            away_team_score=3,
        )
        self.assertGoodTimeline()
        record = self.get_context("record")
        self.assertEqual(record["played"], 1)
        self.assertEqual(record["win"], 1)
        self.assertResponseContains(
            "Played 1: 1 win, 0 losses, 0 draws.", html=False
        )

    def test_team_timeline_undecided_matches(self):
        finals = factories.StageFactory.create(
            division=self.stage.division, follows=self.stage
        )
        home = factories.UndecidedTeamFactory.create(stage=finals, formula="P1")
        away = factories.UndecidedTeamFactory.create(stage=finals, formula="P2")
        factories.MatchFactory.create(
            stage=finals,
            home_team=None,
            away_team=None,
            home_team_undecided=home,
            away_team_undecided=away,
            date="2022-07-03",
            time="09:00",
            datetime="2022-07-03 09:00",
        )
        self.assertGoodTimeline()
        undecided = self.get_context("undecided_by_date")
        self.assertEqual(sum(len(each) for each in undecided.values()), 1)

    def test_team_timeline_no_matches(self):
        self.assertGoodTimeline()
        self.assertEqual(self.get_context("timeline"), [])

    def test_team_timeline_draft_division(self):
        team = factories.TeamFactory.create(
            division__season=self.season, division__draft=True
        )
        self.get(
            "competition:team-timeline",
            self.season.competition.slug,
            self.season.slug,
            team.division.slug,
            team.slug,
        )
        self.response_404()


class MatchesTimelineTests(TestCase):
    """
    Unit coverage for the matches_timeline helper — the incoming mapping
    is ordered by stage and round, not by time, so the helper must
    re-sort each day chronologically.
    """

    def test_out_of_order_matches_are_sorted_chronologically(self):
        early = Match(datetime=datetime(2022, 7, 2, 9, 0, tzinfo=timezone.utc))
        late = Match(datetime=datetime(2022, 7, 2, 12, 0, tzinfo=timezone.utc))
        by_date = collections.OrderedDict([(early.datetime.date(), [late, early])])

        timeline = matches_timeline(by_date)

        items = timeline[0]["items"]
        self.assertEqual(items[0]["match"], early)
        self.assertEqual(items[1]["match"], late)
        self.assertIsNone(items[0]["gap"])
        self.assertEqual(items[1]["gap"].total_seconds(), 3 * 60 * 60)
        self.assertEqual(str(items[1]["gap_display"]), "3h")

    def test_bye_sorts_last_and_does_not_interrupt_gap(self):
        early = Match(datetime=datetime(2022, 7, 2, 9, 0, tzinfo=timezone.utc))
        late = Match(datetime=datetime(2022, 7, 2, 12, 0, tzinfo=timezone.utc))
        bye = Match(is_bye=True)
        by_date = collections.OrderedDict(
            [(early.datetime.date(), [bye, late, early])]
        )

        timeline = matches_timeline(by_date)

        items = timeline[0]["items"]
        self.assertEqual(items[0]["match"], early)
        self.assertEqual(items[1]["match"], late)
        self.assertEqual(items[2]["match"], bye)
        self.assertEqual(str(items[1]["gap_display"]), "3h")
        self.assertIsNone(items[2]["gap"])
