import datetime
import unittest
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
from tournamentcontrol.competition.models import Division
from tournamentcontrol.competition.tests.factories import (
    MatchFactory,
    SeasonFactory,
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
        with self.subTest(test_stage=test_stage):
            res = matches_require_basic_results()
            self.assertCountEqual(
                res.values_list("home_team_title", "away_team_title"),
                result_required_expected,
                "1: Unexpected values from 'matches_require_basic_results'",
            )
        with self.subTest(test_stage=test_stage):
            res = matches_require_progression()
            self.assertCountEqual(
                res.values_list("home_team_title", "away_team_title"),
                require_progression_expected,
                "2: Unexpected values from 'matches_require_progression'",
            )
        with self.subTest(test_stage=test_stage):
            res = matches_progression_possible()
            self.assertCountEqual(
                res,
                possible_progression_expected,
                "3: Unexpected values from 'matches_progression_possible'",
            )
        with self.subTest(test_stage=test_stage):
            res = stages_require_progression()
            self.assertEqual(
                res,
                stage_progression_expected,
                "4: Unexpected values from 'stages_require_progression'",
            )

    def test_trivial(self):
        # Need two match times, one in the past and one in the future.
        dt1 = datetime.datetime(2019, 7, 15, 8, 30, tzinfo=ZoneInfo("UTC"))
        dt2 = datetime.datetime(2019, 7, 15, 10, 30, tzinfo=ZoneInfo("UTC"))
        dt3 = datetime.datetime(2019, 7, 15, 12, 30, tzinfo=ZoneInfo("UTC"))

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

    def test_unrelated_bug(self):
        season = SeasonFactory.create()
        with self.login(self.superuser):
            add_division = Division(season=season).url_names["add"]
            self.get_check_200(add_division.url_name, *add_division.args)
            data = {
                "title": "Example",
                "short_title": "",
                "rank_division": "",
                "copy": "",
                "draft": "0",
                "points_formula_0": "3",
                "points_formula_1": "2",
                "points_formula_2": "1",
                "points_formula_3": "",
                "points_formula_4": "",
                "points_formula_5": "",
                "bonus_points_formula": "",
                "forfeit_for_score": "5",
                "forfeit_against_score": "0",
                "include_forfeits_in_played": "1",
                "slug": "",
                "slug_locked": "0",
            }
            self.post(add_division.url_name, *add_division.args, data=data)
            self.assertRedirects(self.last_response, season.urls["edit"])

    def test_qualifier_placement(self):
        """Test progression for qualifying matches that need to be evaluated in order.

        This test verifies the scenario described in issue #62:
        - P3 vs P6 (QUAL 1)
        - P4 vs P5 (QUAL 2)
        - P1 vs Lower placed qualifier
        - P2 vs Higher placed qualifier
        """
        # Need match times in the past
        dt1 = datetime.datetime(2019, 7, 15, 8, 30, tzinfo=ZoneInfo("UTC"))
        dt2 = datetime.datetime(2019, 7, 15, 10, 30, tzinfo=ZoneInfo("UTC"))

        # Create a round-robin stage and a final series stage
        rounds = StageFactory.create(
            division__season__timezone="UTC", order=1, keep_ladder=True
        )
        finals = StageFactory.create(division=rounds.division, order=2)

        # Create teams for the division
        teams = TeamFactory.create_batch(6, division=finals.division)
        t1, t2, t3, t4, t5, t6 = teams

        # Create the undecided teams for the stage
        lpq = finals.undecided_teams.create(label="Lower Placed Qualifier")
        hpq = finals.undecided_teams.create(label="Higher Placed Qualifier")

        # Fake out playing games from round stage by setting up ladder summaries
        # for teams (simulating result entries)
        rounds.ladder_summary.create(team=t1, played=5, win=5, loss=0, points=15)
        rounds.ladder_summary.create(team=t2, played=5, win=4, loss=0, points=13)
        rounds.ladder_summary.create(team=t3, played=5, win=3, loss=0, points=11)
        rounds.ladder_summary.create(team=t4, played=5, win=2, loss=0, points=9)
        rounds.ladder_summary.create(team=t5, played=5, win=1, loss=0, points=7)
        rounds.ladder_summary.create(team=t6, played=5, win=0, loss=0, points=5)

        # Create qualifying matches:
        # P3 vs P6 (QUAL 1)
        qual1 = MatchFactory.create(
            stage=finals,
            home_team=None,
            home_team_eval="P3",
            away_team=None,
            away_team_eval="P6",
            datetime=dt1,
            label="QUAL 1",
        )

        # P4 vs P5 (QUAL 2)
        qual2 = MatchFactory.create(
            stage=finals,
            home_team=None,
            home_team_eval="P4",
            away_team=None,
            away_team_eval="P5",
            datetime=dt1,
            label="QUAL 2",
        )

        # Create semi-final matches with undecided teams:
        # P1 vs Lower placed qualifier
        semi1 = MatchFactory.create(
            stage=finals,
            home_team=None,
            home_team_eval="P1",
            away_team=None,  # Undecided - lower placed qualifier
            datetime=dt2,
            label="Semi 1",
            away_team_undecided=lpq,  # Lower Placed Qualifier
        )

        # P2 vs Higher placed qualifier
        semi2 = MatchFactory.create(
            stage=finals,
            home_team=None,
            home_team_eval="P2",
            away_team=None,  # Undecided - higher placed qualifier
            datetime=dt2,
            label="Semi 2",
            away_team_undecided=hpq,  # Higher Placed Qualifier
        )

        progress_stage = finals.url_names["progress"]
        result_view_kwargs = {
            "competition_id": finals.division.season.competition.pk,
            "season_id": finals.division.season.pk,
            "datestr": dt1.strftime("%Y%m%d"),
        }

        with freeze_time("2019-07-14 19:00 UTC"), self.login(self.superuser):
            self.assertProgression(
                "1: setup, after rounds, before any progressions",
                [],
                [
                    ("3rd", "6th"),
                    ("4th", "5th"),
                    ("1st", "Lower Placed Qualifier"),
                    ("2nd", "Higher Placed Qualifier"),
                ],
                [qual1, qual2, semi1, semi2],
                {finals.division: {finals: [qual1, qual2, semi1, semi2]}},
            )
            self.get_check_200("admin:index")
            self.assertResponseNotContains(
                f'<a href="{finals.division.season.urls["edit"]}{dt1.strftime("%Y%m%d")}/results/">{dt1.strftime("%B %d, %Y")}</a>'
            )
            self.assertResponseContains(
                f'<a href="{finals.urls["progress"]}">{finals.title}</a>'
            )

        with self.login(self.superuser):
            self.get_check_200(progress_stage.url_name, *progress_stage.args)
            self.post(
                progress_stage.url_name,
                *progress_stage.args,
                data={
                    "form-TOTAL_FORMS": "4",
                    "form-INITIAL_FORMS": "4",
                    "form-MIN_NUM_FORMS": "0",
                    "form-MAX_NUM_FORMS": "1000",
                    "form-0-id": qual1.pk,
                    "form-0-home_team": t3.pk,
                    "form-0-away_team": t6.pk,
                    "form-1-id": qual2.pk,
                    "form-1-home_team": t4.pk,
                    "form-1-away_team": t5.pk,
                    "form-2-id": semi1.pk,
                    "form-2-home_team": t1.pk,
                    "form-2-away_team": "",
                    "form-3-id": semi2.pk,
                    "form-3-home_team": t2.pk,
                    "form-3-away_team": "",
                },
            )
            self.response_302()

        with freeze_time("2019-07-15 09:30 UTC"):
            self.assertProgression(
                "2: after qualifier start time, before result entry",
                [(t3.title, t6.title), (t4.title, t5.title)],
                [
                    (t1.title, "Lower Placed Qualifier"),
                    (t2.title, "Higher Placed Qualifier"),
                ],
                # Progression is possible into the semi-finals because the away
                # team is an undecided team based off a label as opposed to a
                # formula.
                [semi1, semi2],
                {finals.division: {finals: [semi1, semi2]}},
            )

        with self.login(self.superuser):
            self.get_check_200(
                "admin:competition:match-results",
                timestr=dt1.strftime("%H%M"),
                **result_view_kwargs,
            )
            self.post(
                "admin:competition:match-results",
                timestr=dt1.strftime("%H%M"),
                data={
                    "matches-TOTAL_FORMS": "2",
                    "matches-INITIAL_FORMS": "2",
                    "matches-MIN_NUM_FORMS": "0",
                    "matches-MAX_NUM_FORMS": "1000",
                    "byes-TOTAL_FORMS": "0",
                    "byes-INITIAL_FORMS": "0",
                    "byes-MIN_NUM_FORMS": "0",
                    "byes-MAX_NUM_FORMS": "1000",
                    "matches-0-id": qual1.pk,
                    # Upset in the 3rd vs 6th match
                    "matches-0-home_team_score": "1",
                    "matches-0-away_team_score": "3",
                    "matches-0-is_forfeit": "0",
                    "matches-0-forfeit_winner": "",
                    # Expected result in the 4th vs 5th match
                    "matches-1-id": qual2.pk,
                    "matches-1-home_team_score": "2",
                    "matches-1-away_team_score": "0",
                    "matches-1-is_forfeit": "0",
                    "matches-1-forfeit_winner": "",
                },
                **result_view_kwargs,
            )
            self.response_302()

        # Now both qualification matches are complete, progression should be possible
        with freeze_time("2019-07-15 09:30 UTC"):
            self.assertProgression(
                "3: after qualifiers results posted, before semi progression",
                [],
                [
                    (t1.title, "Lower Placed Qualifier"),
                    (t2.title, "Higher Placed Qualifier"),
                ],
                [semi1, semi2],
                {finals.division: {finals: [semi1, semi2]}},
            )

        # Now we can progress the semi-finals
        with self.login(self.superuser):
            self.get_check_200(progress_stage.url_name, *progress_stage.args)
            self.post(
                progress_stage.url_name,
                *progress_stage.args,
                data={
                    "form-TOTAL_FORMS": 2,
                    "form-INITIAL_FORMS": 2,
                    "form-MIN_NUM_FORMS": 0,
                    "form-MAX_NUM_FORMS": 1000,
                    # Upset in qual 1 means HPQ is now t4 and LPQ is t6
                    # No home_team fields because they are popped from the form
                    # (they were set in the first progression)
                    "form-0-id": semi1.pk,
                    "form-0-team": t6.pk,
                    "form-1-id": semi2.pk,
                    "form-1-team": t4.pk,
                },
            )
            self.response_302()

        with freeze_time("2019-07-15 09:30 UTC"):
            self.assertProgression(
                "4: after semi progression, before played",
                [
                    (t1.title, t6.title),
                    (t2.title, t4.title),
                ],
                [],
                [],
                {},
            )

        # Add a Bronze and Gold Medal game which will use winners and losers
        # from the semis.
