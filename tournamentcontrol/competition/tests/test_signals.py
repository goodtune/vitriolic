import importlib

from django.apps import apps
from django.test import TestCase

from tournamentcontrol.competition.models import LadderEntry, LadderSummary
from tournamentcontrol.competition.tests import factories

# The repair migration is named with a numeric prefix so it cannot be imported
# with the ``from ... import ...`` syntax.
repair = importlib.import_module(
    "tournamentcontrol.competition.migrations"
    ".0062_fix_cross_stage_ladder_summary_pool"
)


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

    def test_repair_migration_detaches_cross_stage_pool(self):
        # Reproduce the data as it was written before the signal was fixed;
        # the summary took the pool from the team, not from its own stage.
        for summary in LadderSummary.objects.filter(stage=self.m55_stage):
            summary.stage_group = summary.team.stage_group
            summary.save(update_fields=["stage_group"])

        self.assertEqual(6, self.pool_a.ladder_summary.count())
        self.assertEqual(4, self.pool_b.ladder_summary.count())

        repair.clear_cross_stage_stage_group(apps, None)

        self.assertEqual(4, self.pool_a.ladder_summary.count())
        self.assertEqual(3, self.pool_b.ladder_summary.count())
        self.assertQuerySetEqual(
            LadderSummary.objects.filter(stage=self.m55_stage).values_list(
                "stage_group", flat=True
            ),
            [None, None, None],
        )
