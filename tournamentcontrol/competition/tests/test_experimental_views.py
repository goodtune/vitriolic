import collections
from datetime import datetime, timezone

from django.test import override_settings
from test_plus import TestCase

from tournamentcontrol.competition.models import Match
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.utils import matches_timeline


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
        self.assertEqual(self.last_response.context["match_count"], 5)

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
        self.assertEqual(self.last_response.context["match_count"], 3)

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
        self.assertEqual(self.last_response.context["match_count"], 1)

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
        self.assertEqual(self.last_response.context["match_count"], 1)

        # the venue includes matches on all of its grounds
        self.assertGoodView(
            "competition:season-fixtures",
            self.season.competition.slug,
            self.season.slug,
            data={"place": venue.pk},
        )
        self.assertEqual(self.last_response.context["match_count"], 2)

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
        self.assertEqual(self.last_response.context["match_count"], 1)
        self.assertCountEqual(
            self.last_response.context["divisions"], [stage.division]
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
        self.assertEqual(self.last_response.context["match_count"], 1)


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

        timeline = self.last_response.context["timeline"]
        self.assertEqual(len(timeline), 1)
        items = timeline[0]["items"]
        self.assertEqual(len(items), 2)

        # first match of the day carries no rest gap, the second reports
        # the time since the earlier start
        self.assertIsNone(items[0]["gap"])
        self.assertEqual(str(items[1]["gap_display"]), "3h")

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
        record = self.last_response.context["record"]
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
        undecided = self.last_response.context["undecided_by_date"]
        self.assertEqual(sum(len(each) for each in undecided.values()), 1)

    def test_team_timeline_no_matches(self):
        self.assertGoodTimeline()
        self.assertEqual(self.last_response.context["timeline"], [])

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
