import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone
from freezegun import freeze_time
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.dashboard import (
    matches_progression_possible,
    matches_require_basic_results,
    matches_require_progression,
    stages_require_progression,
)
from tournamentcontrol.competition.tests.factories import (
    MatchFactory,
    StageFactory,
    TeamFactory,
)


class BasicResultTests(TestCase):
    @freeze_time("2019-07-15 09:00 UTC")
    def test_bare_all_in_utc(self):
        match = MatchFactory.create(
            datetime=datetime.datetime(2019, 7, 15, 8, 30, tzinfo=ZoneInfo("UTC")),
            stage__division__season__timezone="UTC",
        )
        self.assertCountEqual(matches_require_basic_results(), [match])

    @freeze_time("2019-07-15 09:00 +13")
    def test_bare_match_in_samoa(self):
        tzname = "Pacific/Apia"
        tzinfo = ZoneInfo(tzname)
        match = MatchFactory.create(
            datetime=timezone.make_aware(datetime.datetime(2019, 7, 15, 8, 30), tzinfo),
            stage__division__season__timezone=tzname,
        )
        self.assertCountEqual(matches_require_basic_results(), [match])

    @freeze_time("2019-07-15 09:00 +13")
    def test_bare_match_in_samoa_bye(self):
        tzname = "Pacific/Apia"
        tzinfo = ZoneInfo(tzname)
        match = MatchFactory.create(
            round=1,
            is_bye=True,
            away_team=None,
            datetime=None,
            date=datetime.date(2019, 7, 15),
            time=None,
            stage__division__season__timezone=tzname,
        )
        # A bye's would never exist in isolation.
        MatchFactory.create(
            round=1,
            datetime=timezone.make_aware(datetime.datetime(2019, 7, 15, 8, 30), tzinfo),
            stage=match.stage,
            home_team_score=5,
            away_team_score=4,
        )
        self.assertCountEqual(matches_require_basic_results(), [match])


@freeze_time("2019-07-15 09:30 UTC")
class RequireProgression(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def assertProgression(
        self,
        test_stage,
        result_required_expected,
        require_progression_expected,
        possible_progression_expected,
        stage_progression_expected,
    ):
        with self.subTest(matches_require_basic_results=test_stage):
            res = matches_require_basic_results()
            self.assertCountEqual(
                res.values_list("home_team_title", "away_team_title"),
                result_required_expected,
            )
        with self.subTest(matches_require_progression=test_stage):
            res = matches_require_progression()
            self.assertCountEqual(
                res.values_list("home_team_title", "away_team_title"),
                require_progression_expected,
            )
        with self.subTest(matches_progression_possible=test_stage):
            res = matches_progression_possible()
            self.assertCountEqual(res, possible_progression_expected)
        with self.subTest(stages_require_progression=test_stage):
            res = stages_require_progression()
            self.assertEqual(res, stage_progression_expected)

    def test_trivial(self):
        # Need two match times, one in the past and one in the future.
        dt1 = datetime.datetime(2019, 7, 15, 8, 30, tzinfo=ZoneInfo("UTC"))
        dt2 = datetime.datetime(2019, 7, 15, 10, 30, tzinfo=ZoneInfo("UTC"))

        # Create a stage with four teams to play each other and then progress
        # the winners to a final.
        rounds = StageFactory.create(division__season__timezone="UTC", order=1)
        finals = StageFactory.create(division=rounds.division, order=2)
        t1, t2, t3, t4 = TeamFactory.create_batch(4, division=finals.division)

        # Semi Final
        m1 = MatchFactory.create(
            stage=finals, home_team=t1, away_team=t4, datetime=dt1, label="Semi 1"
        )
        m2 = MatchFactory.create(
            stage=finals, home_team=t2, away_team=t3, datetime=dt1, label="Semi 2"
        )
        # Final
        m3 = MatchFactory.create(
            stage=finals,
            home_team=None,
            away_team=None,
            home_team_eval="W",
            home_team_eval_related=m1,
            away_team_eval="W",
            away_team_eval_related=m2,
            datetime=dt2,
            label="Final",
        )

        self.assertProgression(
            "setup",
            [(t1.title, t4.title), (t2.title, t3.title)],
            [("Winner Semi 1", "Winner Semi 2")],
            [],  # progress not possible, semi not played
            {},
        )

        # Home teams win both matches 4-3
        for match in [m1, m2]:
            match.home_team_score = 4
            match.away_team_score = 3
            match.save()

        self.assertProgression(
            "after semis",
            [],
            [("Winner Semi 1", "Winner Semi 2")],
            [m3],  # semi results entered
            {finals.division: {finals: [m3]}},  # stage needs progressing
        )

        m3.home_team, m3.away_team = m1.home_team, m2.home_team
        m3.save()

        self.assertProgression("before final", [], [], [], {})
