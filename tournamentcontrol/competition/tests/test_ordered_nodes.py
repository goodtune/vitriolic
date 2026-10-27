"""
The order of the rows kept in a list together: a division's stages and teams,
a stage's pools, a season's divisions.

A row moves past its real neighbour in the list, whatever the ``order``
values are: they are not kept dense, so a row that is deleted leaves a gap. A
division's stages and teams may not share a value, since a formula names a
stage by its number in the list.
"""

from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from test_plus import TestCase

from tournamentcontrol.competition.models import Stage, Team
from tournamentcontrol.competition.tests import factories


class MoveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.division = factories.DivisionFactory.create()
        cls.stages = [
            factories.StageFactory.create(division=cls.division, title=title, order=n)
            for n, title in ((1, "Pool play"), (3, "Semi-finals"), (5, "Finals"))
        ]
        # A stage of another division in the same season, numbered between
        # them, is not a neighbour of any of them.
        cls.other = factories.StageFactory.create(
            division=factories.DivisionFactory.create(season=cls.division.season),
            order=2,
        )

    def orders(self):
        return list(self.division.stages.values_list("title", "order"))

    def test_a_stage_moves_down_past_the_gap(self):
        pool_play, semi_finals, finals = self.stages
        semi_finals.move_down()
        self.assertEqual(
            self.orders(), [("Pool play", 1), ("Finals", 3), ("Semi-finals", 5)]
        )

    def test_a_stage_moves_up_past_the_gap(self):
        pool_play, semi_finals, finals = self.stages
        semi_finals.move_up()
        self.assertEqual(
            self.orders(), [("Semi-finals", 1), ("Pool play", 3), ("Finals", 5)]
        )

    def test_the_first_stage_has_nothing_above_it(self):
        self.stages[0].move_up()
        self.assertEqual(
            self.orders(), [("Pool play", 1), ("Semi-finals", 3), ("Finals", 5)]
        )

    def test_the_last_stage_has_nothing_below_it(self):
        self.stages[-1].move_down()
        self.assertEqual(
            self.orders(), [("Pool play", 1), ("Semi-finals", 3), ("Finals", 5)]
        )

    def test_a_stage_of_another_division_is_not_a_neighbour(self):
        self.stages[0].move_down()
        self.other.refresh_from_db()
        self.assertEqual(self.other.order, 2)

    def test_a_pool_moves_among_the_pools_of_its_own_stage(self):
        pool_play, semi_finals, finals = self.stages
        a, b = [
            factories.StageGroupFactory.create(stage=pool_play, title=title, order=n)
            for n, title in ((1, "Pool A"), (2, "Pool B"))
        ]
        c, d = [
            factories.StageGroupFactory.create(stage=semi_finals, title=title, order=n)
            for n, title in ((1, "Pool C"), (2, "Pool D"))
        ]
        a.move_down()
        self.assertEqual(
            list(pool_play.pools.values_list("title", "order")),
            [("Pool B", 1), ("Pool A", 2)],
        )
        self.assertEqual(
            list(semi_finals.pools.values_list("title", "order")),
            [("Pool C", 1), ("Pool D", 2)],
        )

    def test_rows_sharing_a_value_are_renumbered_as_one_moves(self):
        # Divisions of a season may still share a value; the one that is
        # moved and its neighbour are told apart by their keys.
        season = factories.SeasonFactory.create()
        first, second, third = [
            factories.DivisionFactory.create(season=season, title=title, order=n)
            for n, title in ((2, "Men's"), (2, "Women's"), (5, "Mixed"))
        ]
        second.move_down()
        self.assertEqual(
            list(season.divisions.values_list("title", "order")),
            [("Men's", 1), ("Mixed", 2), ("Women's", 3)],
        )

    def test_a_row_sharing_a_value_moves_up_past_the_other(self):
        season = factories.SeasonFactory.create()
        first, second, third = [
            factories.DivisionFactory.create(season=season, title=title, order=n)
            for n, title in ((2, "Men's"), (2, "Women's"), (5, "Mixed"))
        ]
        second.move_up()
        self.assertEqual(
            list(season.divisions.values_list("title", "order")),
            [("Women's", 1), ("Men's", 2), ("Mixed", 3)],
        )


class UniqueOrderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.division = factories.DivisionFactory.create()

    def test_two_stages_of_a_division_may_not_share_an_order(self):
        factories.StageFactory.create(division=self.division, order=1)
        with self.assertRaisesMessage(
            IntegrityError, "competition_stage_unique_division_order"
        ):
            Stage.objects.create(
                division=self.division, title="Second", slug="second", order=1
            )

    def test_two_teams_of_a_division_may_not_share_an_order(self):
        factories.TeamFactory.create(division=self.division, order=1)
        with self.assertRaisesMessage(
            IntegrityError, "competition_team_unique_division_order"
        ):
            Team.objects.create(
                division=self.division, title="Second", slug="second", order=1
            )


class MigrationTests(TransactionTestCase):
    """
    Stages and teams of a division that share an ``order`` are renumbered in
    the order they were listed before the constraint is added; a division
    whose rows are already distinct is left as it is, gaps and all.
    """

    migrate_from = [("competition", "0069_list_ordering")]
    migrate_to = [("competition", "0070_unique_order")]

    def test_rows_sharing_an_order_are_renumbered(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        Competition = apps.get_model("competition", "Competition")
        Season = apps.get_model("competition", "Season")
        Division = apps.get_model("competition", "Division")
        Stage = apps.get_model("competition", "Stage")
        Team = apps.get_model("competition", "Team")

        competition = Competition.objects.create(title="Touch", slug="touch")
        season = Season.objects.create(
            competition=competition, title="2026", slug="2026"
        )
        shared = Division.objects.create(season=season, title="Shared", slug="shared")
        gapped = Division.objects.create(season=season, title="Gapped", slug="gapped")
        for n, title in ((2, "Pool play"), (2, "Semi-finals"), (5, "Finals")):
            Stage.objects.create(
                division=shared, title=title, slug=title.lower(), order=n
            )
        for n, title in ((1, "Pool play"), (3, "Finals")):
            Stage.objects.create(
                division=gapped, title=title, slug=title.lower(), order=n
            )
        for n, title in ((1, "Ants"), (1, "Bees"), (1, "Cats")):
            Team.objects.create(
                division=shared, title=title, slug=title.lower(), order=n
            )

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        Stage = apps.get_model("competition", "Stage")
        Team = apps.get_model("competition", "Team")

        self.assertEqual(
            list(
                Stage.objects.filter(division_id=shared.pk)
                .order_by("order")
                .values_list("title", "order")
            ),
            [("Pool play", 1), ("Semi-finals", 2), ("Finals", 3)],
        )
        self.assertEqual(
            list(
                Stage.objects.filter(division_id=gapped.pk)
                .order_by("order")
                .values_list("title", "order")
            ),
            [("Pool play", 1), ("Finals", 3)],
        )
        self.assertEqual(
            list(
                Team.objects.filter(division_id=shared.pk)
                .order_by("order")
                .values_list("title", "order")
            ),
            [("Ants", 1), ("Bees", 2), ("Cats", 3)],
        )

        # Migrate everything else forward again so later tests see the
        # expected schema.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
