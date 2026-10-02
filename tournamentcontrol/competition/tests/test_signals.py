from django.test import TestCase

from tournamentcontrol.competition.models import LadderEntry, LadderSummary
from tournamentcontrol.competition.tests import factories


class SignalHandlerTests(TestCase):
    def test_ladder_entry_match_no_score(self):
        factories.MatchFactory.create()
        self.assertQuerySetEqual(LadderEntry.objects.all(), LadderEntry.objects.none())

    def test_ladder_entry_match_with_score(self):
        factories.MatchFactory.create(home_team_score=5, away_team_score=2)
        self.assertCountEqual(
            [
                (1, 0, 0, 5, 2, 3, 3),
                (0, 1, 0, 2, 5, -3, 3),
            ],
            LadderEntry.objects.values_list(
                "win", "loss", "draw", "score_for", "score_against", "diff", "margin"
            ),
        )

    def test_ladder_summary_3_match_series(self):
        # seed a match which will produce all required relations
        match = factories.MatchFactory.create(home_team_score=5, away_team_score=2)

        # build two more matches with known results to produce LadderSummary
        factories.MatchFactory.create(
            home_team=match.home_team,
            home_team_score=3,
            away_team=match.away_team,
            away_team_score=4,
            stage=match.stage,
        )
        factories.MatchFactory.create(
            home_team=match.home_team,
            home_team_score=2,
            away_team=match.away_team,
            away_team_score=2,
            stage=match.stage,
        )

        self.assertCountEqual(
            [
                (3, 1, 1, 1, 10, 8, 2),
                (3, 1, 1, 1, 8, 10, -2),
            ],
            LadderSummary.objects.values_list(
                "played",
                "win",
                "loss",
                "draw",
                "score_for",
                "score_against",
                "difference",
            ),
        )


class BonusPointsFormulaTests(TestCase):
    """
    Bonus points formulas may reference ``margin`` (and ``diff``), which are
    normally only available as queryset annotations. The signal handler must
    make them available on the freshly built LadderEntry before evaluation.
    """

    def setUp(self):
        self.division = factories.DivisionFactory.create(
            points_formula="3*win + 2*draw + 1*loss",
            bonus_points_formula="[loss=1, margin<=2: 1]",
        )
        self.stage = factories.StageFactory.create(division=self.division)
        self.home = factories.TeamFactory.create(division=self.division)
        self.away = factories.TeamFactory.create(division=self.division)

    def _play(self, home_score, away_score):
        return factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.home,
            away_team=self.away,
            home_team_score=home_score,
            away_team_score=away_score,
        )

    def _ladder(self, match):
        return {
            entry.team_id: (entry.win, entry.loss, entry.bonus_points, entry.points)
            for entry in match.ladder_entries.all()
        }

    def test_narrow_loss_earns_losing_bonus(self):
        match = self._play(4, 5)
        self.assertEqual(
            {self.home.pk: (0, 1, 1, 2), self.away.pk: (1, 0, 0, 3)},
            self._ladder(match),
        )

    def test_two_point_loss_earns_losing_bonus(self):
        match = self._play(7, 5)
        self.assertEqual(
            {self.home.pk: (1, 0, 0, 3), self.away.pk: (0, 1, 1, 2)},
            self._ladder(match),
        )

    def test_wide_loss_earns_no_losing_bonus(self):
        match = self._play(3, 7)
        self.assertEqual(
            {self.home.pk: (0, 1, 0, 1), self.away.pk: (1, 0, 0, 3)},
            self._ladder(match),
        )

    def test_shutout_loss_earns_no_losing_bonus(self):
        match = self._play(6, 0)
        self.assertEqual(
            {self.home.pk: (1, 0, 0, 3), self.away.pk: (0, 1, 0, 1)},
            self._ladder(match),
        )

    def test_diff_available_to_bonus_formula(self):
        self.division.bonus_points_formula = "[diff>=5: 1]"
        self.division.save()
        match = self._play(8, 2)
        self.assertEqual(
            {self.home.pk: (1, 0, 1, 4), self.away.pk: (0, 1, 0, 1)},
            self._ladder(match),
        )


class CombinedAgeGradeLadderTests(TestCase):
    """
    Model the "Mens 50/55" structure used at Euros 2026.

    Two age grades were combined into a single division; the first stage is a
    pool stage mixing M50 and M55 teams, and the second stage is a M55-only
    round robin (no pools) which picks up the M55 fixtures that were not
    played in the pool stage.

    Teams keep a ``stage_group`` pointing at their pool from the first stage,
    so the ladder summaries built for the second stage must not be attributed
    to that pool.
    """

    def setUp(self):
        self.division = factories.DivisionFactory.create(title="Mens 50/55")

        self.pool_stage = factories.StageFactory.create(
            division=self.division, title="Pool Play", order=1
        )
        self.pool_a = factories.StageGroupFactory.create(
            stage=self.pool_stage, title="Pool A", order=1
        )
        self.pool_b = factories.StageGroupFactory.create(
            stage=self.pool_stage, title="Pool B", order=2
        )

        self.m55_stage = factories.StageFactory.create(
            division=self.division, title="Mens 55", order=2
        )

        # Pool A has two M50 teams and two M55 teams.
        self.m50_a1, self.m50_a2 = [
            factories.TeamFactory.create(
                division=self.division, stage_group=self.pool_a
            )
            for _ in range(2)
        ]
        self.m55_a1, self.m55_a2 = [
            factories.TeamFactory.create(
                division=self.division, stage_group=self.pool_a
            )
            for _ in range(2)
        ]

        # Pool B has two M50 teams and one M55 team.
        self.m50_b1, self.m50_b2 = [
            factories.TeamFactory.create(
                division=self.division, stage_group=self.pool_b
            )
            for _ in range(2)
        ]
        self.m55_b1 = factories.TeamFactory.create(
            division=self.division, stage_group=self.pool_b
        )

        # Round robin in each pool, except the M55 v M55 fixture in Pool A
        # which is deferred to the second stage so it is not duplicated.
        pool_a_teams = [self.m50_a1, self.m50_a2, self.m55_a1, self.m55_a2]
        for index, home in enumerate(pool_a_teams):
            for away in pool_a_teams[index + 1 :]:
                if {home, away} == {self.m55_a1, self.m55_a2}:
                    continue
                factories.MatchFactory.create(
                    stage=self.pool_stage,
                    stage_group=self.pool_a,
                    home_team=home,
                    home_team_score=5,
                    away_team=away,
                    away_team_score=3,
                )

        pool_b_teams = [self.m50_b1, self.m50_b2, self.m55_b1]
        for index, home in enumerate(pool_b_teams):
            for away in pool_b_teams[index + 1 :]:
                factories.MatchFactory.create(
                    stage=self.pool_stage,
                    stage_group=self.pool_b,
                    home_team=home,
                    home_team_score=4,
                    away_team=away,
                    away_team_score=2,
                )

        # Second stage; a round robin of the three M55 teams, including the
        # fixture uprooted from Pool A.
        m55_teams = [self.m55_a1, self.m55_a2, self.m55_b1]
        for index, home in enumerate(m55_teams):
            for away in m55_teams[index + 1 :]:
                factories.MatchFactory.create(
                    stage=self.m55_stage,
                    home_team=home,
                    home_team_score=6,
                    away_team=away,
                    away_team_score=1,
                )

    def test_second_stage_summary_has_no_stage_group(self):
        self.assertQuerySetEqual(
            LadderSummary.objects.filter(stage=self.m55_stage).values_list(
                "stage_group", flat=True
            ),
            [None, None, None],
        )

    def test_pool_ladder_only_contains_own_stage(self):
        for pool, expected in ((self.pool_a, 4), (self.pool_b, 3)):
            with self.subTest(pool=pool.title):
                summary = pool.ladder_summary.all()
                self.assertEqual(expected, summary.count())
                self.assertQuerySetEqual(
                    summary.values_list("stage", flat=True),
                    [self.pool_stage.pk] * expected,
                )

    def test_division_ladders_do_not_duplicate_teams(self):
        ladders = self.division.ladders()

        pools = ladders[self.pool_stage]
        self.assertEqual(
            [self.m50_a1, self.m50_a2, self.m55_a1, self.m55_a2],
            sorted((s.team for s in pools[self.pool_a]), key=lambda t: t.pk),
        )
        self.assertEqual(
            [self.m50_b1, self.m50_b2, self.m55_b1],
            sorted((s.team for s in pools[self.pool_b]), key=lambda t: t.pk),
        )

        self.assertEqual(
            [self.m55_a1, self.m55_a2, self.m55_b1],
            sorted((s.team for s in ladders[self.m55_stage]), key=lambda t: t.pk),
        )


class ChangedLadderFormulaTests(TestCase):
    """
    Editing the fields of a Division that feed into the ladder calculation
    must trigger a rebuild of the LadderEntry records for every match in the
    division that already has a result.
    """

    def setUp(self):
        self.division = factories.DivisionFactory.create(
            points_formula="3*win + 2*draw + 1*loss",
            bonus_points_formula="[loss=1: 1]",
        )
        self.stage = factories.StageFactory.create(division=self.division)
        self.match = factories.MatchFactory.create(
            stage=self.stage, home_team_score=5, away_team_score=2
        )
        self.home = self.match.home_team
        self.away = self.match.away_team

    def _entry(self, team):
        return LadderEntry.objects.get(match=self.match, team=team)

    def test_initial_bonus_points(self):
        self.assertEqual(self._entry(self.home).bonus_points, 0)
        self.assertEqual(self._entry(self.home).points, 3)
        self.assertEqual(self._entry(self.away).bonus_points, 1)
        self.assertEqual(self._entry(self.away).points, 2)

    def test_changed_bonus_points_formula_recalculates_ladder(self):
        self.division.bonus_points_formula = "[win=1: 2]"
        self.division.save()

        self.assertEqual(self._entry(self.home).bonus_points, 2)
        self.assertEqual(self._entry(self.home).points, 5)
        self.assertEqual(self._entry(self.away).bonus_points, 0)
        self.assertEqual(self._entry(self.away).points, 1)

    def test_cleared_bonus_points_formula_recalculates_ladder(self):
        self.division.bonus_points_formula = ""
        self.division.save()

        self.assertEqual(self._entry(self.home).bonus_points, 0)
        self.assertEqual(self._entry(self.home).points, 3)
        self.assertEqual(self._entry(self.away).bonus_points, 0)
        self.assertEqual(self._entry(self.away).points, 1)

    def test_changed_points_formula_recalculates_ladder(self):
        self.division.points_formula = "4*win + 2*draw"
        self.division.save()

        self.assertEqual(self._entry(self.home).points, 4)
        self.assertEqual(self._entry(self.away).points, 1)

    def test_changed_include_forfeits_in_played_recalculates_ladder(self):
        forfeit = factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.home,
            away_team=self.away,
            is_forfeit=True,
            forfeit_winner=self.home,
            home_team_score=self.division.forfeit_for_score,
            away_team_score=self.division.forfeit_against_score,
        )
        forfeit_entries = LadderEntry.objects.filter(match=forfeit)
        self.assertEqual(forfeit_entries.get(team=self.away).played, 1)
        self.assertEqual(forfeit_entries.get(team=self.home).played, 1)

        self.division.include_forfeits_in_played = False
        self.division.save()

        self.assertEqual(forfeit_entries.get(team=self.away).played, 0)
        self.assertEqual(forfeit_entries.get(team=self.home).played, 0)
        # the match with a regular result is unaffected
        self.assertEqual(self._entry(self.home).played, 1)

    def test_unrelated_change_does_not_rebuild_ladder(self):
        before = set(LadderEntry.objects.values_list("pk", flat=True))

        self.division.title = "Renamed"
        self.division.save()

        self.assertEqual(before, set(LadderEntry.objects.values_list("pk", flat=True)))
