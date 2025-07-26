import textwrap

from django.contrib.auth.models import User
from django.test import Client
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition import utils
from tournamentcontrol.competition.models import UndecidedTeam
from tournamentcontrol.competition.tests.factories import (
    DivisionFactory,
    StageFactory,
    StageGroupFactory,
    UndecidedTeamFactory,
)


class MessagesTestMixin:
    """
    Mixin stub for testing Django messages.

    Drop once we no longer support Django < 5.0.
    """

    def assertMessages(self, *args, **kwargs): ...


class UtilTests(TestCase):
    def test_round_robin_even(self):
        self.assertEqual(
            [[(1, 4), (2, 3)], [(1, 3), (4, 2)], [(1, 2), (3, 4)]],
            utils.round_robin(range(1, 5)),
        )

    def test_round_robin_odd(self):
        self.assertEqual(
            [[(1, 0), (2, 3)], [(1, 3), (0, 2)], [(1, 2), (3, 0)]],
            utils.round_robin(range(1, 4)),
        )

    def test_round_robin_format_even(self):
        self.assertEqual(
            textwrap.dedent(
                """
                ROUND
                1: 1 vs 4
                2: 2 vs 3
                ROUND
                3: 1 vs 3
                4: 4 vs 2
                ROUND
                5: 1 vs 2
                6: 3 vs 4
                """
            ).strip(),
            utils.round_robin_format(range(1, 5)),
        )

    def test_round_robin_format_integer_input(self):
        """Test that integer input works correctly."""
        result = utils.round_robin_format(4)
        expected = textwrap.dedent(
            """
            ROUND
            1: 1 vs 4
            2: 2 vs 3
            ROUND
            3: 1 vs 3
            4: 4 vs 2
            ROUND
            5: 1 vs 2
            6: 3 vs 4
            """
        ).strip()
        self.assertEqual(expected, result)

    def test_round_robin_format_integer_equals_range(self):
        """Test that round_robin_format(4) equals round_robin_format(range(1, 5))."""
        self.assertEqual(
            utils.round_robin_format(4), utils.round_robin_format(range(1, 5))
        )

    def test_round_robin_format_integer_equals_list(self):
        """Test that round_robin_format(4) equals round_robin_format([1, 2, 3, 4])."""
        self.assertEqual(
            utils.round_robin_format(4), utils.round_robin_format([1, 2, 3, 4])
        )

    def test_round_robin_format_different_sizes(self):
        """Test various team counts to ensure flexibility."""
        # Test with 3 teams (odd number)
        result_3_int = utils.round_robin_format(3)
        result_3_list = utils.round_robin_format([1, 2, 3])
        self.assertEqual(result_3_int, result_3_list)

        # Test with 6 teams
        result_6_int = utils.round_robin_format(6)
        result_6_range = utils.round_robin_format(range(1, 7))
        self.assertEqual(result_6_int, result_6_range)

    def test_round_robin_format_custom_teams(self):
        """Test with custom team identifiers."""
        teams = ["Team A", "Team B", "Team C", "Team D"]
        result = utils.round_robin_format(teams)
        self.assertIn("Team A vs Team D", result)
        self.assertIn("Team B vs Team C", result)

    def test_round_robin_format_with_rounds_parameter(self):
        """Test that the rounds parameter works with both integer and iterable inputs."""
        # Test with integer input and rounds parameter
        result_int = utils.round_robin_format(4, rounds=1)
        result_list = utils.round_robin_format([1, 2, 3, 4], rounds=1)
        self.assertEqual(result_int, result_list)

        # Should only contain the first round
        self.assertEqual(result_int.count("ROUND"), 1)

    def test_round_robin_format_edge_cases(self):
        """Test edge cases."""
        # Single team (though this might not be practical)
        result_1 = utils.round_robin_format(1)
        # Should handle gracefully (will have a bye with 0)
        self.assertIsInstance(result_1, str)

        # Two teams
        result_2_int = utils.round_robin_format(2)
        result_2_list = utils.round_robin_format([1, 2])
        self.assertEqual(result_2_int, result_2_list)

    def test_sum_dict_integer(self):
        d1 = utils.SumDict({"a": 1, "b": 2})
        d2 = utils.SumDict({"b": 1, "c": 2})
        self.assertEqual(d1 + d2, utils.SumDict({"a": 1, "b": 3, "c": 2}))

    def test_revpow(self):
        self.assertEqual(utils.revpow(2**4, 2), 4)


class StageGroupPositionTests(TestCase):
    """
    Tests for the stage_group_position function.
    """

    def test_stage_group_position_with_no_pools_raises_index_error(self):
        """
        Test that stage_group_position raises IndexError when trying to access
        a pool that doesn't exist on a stage.
        """
        # Create a division with multiple stages so we can reference one
        division = DivisionFactory.create()
        stage1 = StageFactory.create(division=division, order=1)
        stage2 = StageFactory.create(division=division, order=2)

        # Stage1 has no pools, but we try to access group 1 from stage1
        # This should raise IndexError because stage1.pools.all() is empty
        # and we try to access index 0 (int("1") - 1)
        with self.assertRaisesRegex(
            IndexError, r"Invalid group 1 for stage .* \(stage has 0 pools\)"
        ):
            utils.stage_group_position(stage2, "S1G1P1")

    def test_stage_group_position_with_insufficient_pools_raises_index_error(self):
        """
        Test that stage_group_position raises IndexError when trying to access
        a pool index that is out of range.
        """
        # Create a division with multiple stages
        division = DivisionFactory.create()
        stage1 = StageFactory.create(division=division, order=1)
        stage2 = StageFactory.create(division=division, order=2)

        # Stage1 has only 1 pool
        StageGroupFactory.create(stage=stage1)  # Creates pool 1

        # Try to access group 2 from stage1 (which doesn't exist)
        # This should raise IndexError because stage1.pools.all() has only 1 item
        # and we try to access index 1 (int("2") - 1)
        with self.assertRaisesRegex(
            IndexError, r"Invalid group 2 for stage .* \(stage has 1 pools\)"
        ):
            utils.stage_group_position(stage2, "S1G2P1")

    def test_stage_group_position_with_valid_pool_succeeds(self):
        """
        Test that stage_group_position works correctly when the pool exists.
        """
        # Create a division with multiple stages
        division = DivisionFactory.create()
        stage1 = StageFactory.create(division=division, order=1)
        stage2 = StageFactory.create(division=division, order=2, follows=stage1)
        stage3 = StageFactory.create(division=division, order=3, follows=stage1)

        # Stage1 has 2 pools
        pool1 = StageGroupFactory.create(stage=stage1)
        pool2 = StageGroupFactory.create(stage=stage1)

        # Test formulas both with and without explicit stage reference
        test_cases = [
            # (from_stage, with_stage_formula, without_stage_formula, expected_stage, expected_group, expected_position)
            (stage2, "S1G1P1", "G1P1", stage1, pool1, 1),
            (stage2, "S1G2P3", "G2P3", stage1, pool2, 3),
            (stage3, "S1G1P1", "G1P1", stage1, pool1, 1),
            (stage3, "S1G2P3", "G2P3", stage1, pool2, 3),
        ]

        for (
            from_stage,
            with_stage_formula,
            without_stage_formula,
            expected_stage,
            expected_group,
            expected_position,
        ) in test_cases:
            with self.subTest(from_stage=from_stage, formula=with_stage_formula):
                # Test with explicit stage reference (e.g., "S1G1P1")
                result_stage, result_group, result_position = (
                    utils.stage_group_position(from_stage, with_stage_formula)
                )
                self.assertEqual(result_stage, expected_stage)
                self.assertEqual(result_group, expected_group)
                self.assertEqual(result_position, expected_position)

            with self.subTest(from_stage=from_stage, formula=without_stage_formula):
                # Test without explicit stage reference (e.g., "G1P1")
                # This should use from_stage.comes_after
                result_stage, result_group, result_position = (
                    utils.stage_group_position(from_stage, without_stage_formula)
                )
                self.assertEqual(result_stage, expected_stage)
                self.assertEqual(result_group, expected_group)
                self.assertEqual(result_position, expected_position)

    def test_edit_stage_view_with_undecided_teams_referencing_missing_pools(self):
        """
        Integration test that exercises the edit_stage admin view where UndecidedTeam
        objects reference pools that don't exist, reproducing the original IndexError.

        This test ensures that the admin view handles the error gracefully after
        the fix, rather than crashing with an IndexError when rendering templates
        that access UndecidedTeam.title or UndecidedTeam.choices properties.
        """
        # Create a superuser for admin access using django-test-plus pattern
        superuser = UserFactory.create(is_staff=True, is_superuser=True)

        # Create a division with multiple stages
        division = DivisionFactory.create()
        stage1 = StageFactory.create(division=division, order=1)
        stage2 = StageFactory.create(division=division, order=2, follows=stage1)

        # Create UndecidedTeam objects that reference pools that don't exist
        # This reproduces the problematic scenario from the issue
        undecided_team_1 = UndecidedTeamFactory.create(
            stage=stage2,
            formula="G1P1",  # References group 1, but stage1 has no pools
            label="Winner Group 1",
        )
        undecided_team_2 = UndecidedTeamFactory.create(
            stage=stage2,
            formula="S1G2P1",  # References stage1 group 2, but stage1 has only 0 pools
            label="Winner Group 2",
        )

        # Build the edit_stage URL using the same pattern as other admin tests
        edit_stage_url = stage2.urls["edit"]

        # Before the fix, accessing these properties would raise IndexError: list index out of range
        # After the fix, they should raise IndexError with a descriptive message

        # Test that the properties raise meaningful IndexError rather than crashing
        with self.subTest(formula="G1P1"):
            with self.assertRaisesRegex(
                IndexError, r"Invalid group 1 for stage .* \(stage has 0 pools\)"
            ):
                _ = undecided_team_1.title  # This accesses stage_group_position

        with self.subTest(formula="S1G2P1"):
            with self.assertRaisesRegex(
                IndexError, r"Invalid group 2 for stage .* \(stage has 0 pools\)"
            ):
                _ = undecided_team_2.title  # This accesses stage_group_position

        # Test that accessing choices also provides meaningful error
        with self.subTest(property="choices", formula="G1P1"):
            with self.assertRaisesRegex(
                IndexError, r"Invalid group 1 for stage .* \(stage has 0 pools\)"
            ):
                _ = undecided_team_1.choices  # This also accesses stage_group_position
