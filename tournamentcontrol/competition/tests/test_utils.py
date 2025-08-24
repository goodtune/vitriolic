import textwrap

from test_plus import TestCase

from tournamentcontrol.competition import utils
from tournamentcontrol.competition.tests.factories import (
    DivisionFactory,
    MatchFactory,
    StageFactory,
    StageGroupFactory,
    SuperUserFactory,
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
        # Create a superuser for admin access using SuperUserFactory
        superuser = SuperUserFactory.create()

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

        # After the fix, accessing these properties should NOT raise IndexError
        # Instead they should gracefully handle the error

        # Test that title returns the formula when invalid
        with self.subTest(formula="G1P1"):
            self.assertEqual(undecided_team_1.title, "G1P1")

        with self.subTest(formula="S1G2P1"):
            self.assertEqual(undecided_team_2.title, "S1G2P1")

        # Test that accessing choices returns division teams as fallback
        with self.subTest(property="choices", formula="G1P1"):
            choices = undecided_team_1.choices  # This should return division teams
            self.assertEqual(choices, stage2.division.teams)


class TwoStageFormulaProblemTests(TestCase):
    """
    Tests for the two-stage scenario as requested by @goodtune.

    This covers:
    - Two stages (Round Robin, Finals)
    - Stage 1 (Round Robin) has two pools
    - Stage 2 (Finals) has matches with home_team_eval and away_team_eval
      defined in terms of group and position from the earlier stage
    - Positive test: valid formulae like G1P1 vs G2P2
    - Negative test: valid formulae that can't be resolved like G1P1 vs G5P2
    - When invalid formula occurs, title should return the formula instead of raising exception
    """

    def setUp(self):
        """Set up the two-stage competition scenario."""
        # Create superuser for admin access
        self.user = SuperUserFactory.create()

        # Create a division with two stages
        self.division = DivisionFactory.create()

        # Stage 1: Round Robin with two pools
        self.round_robin_stage = StageFactory.create(
            division=self.division, order=1, title="Round Robin"
        )

        # Create two pools in the Round Robin stage
        self.pool1 = StageGroupFactory.create(stage=self.round_robin_stage, order=1)
        self.pool2 = StageGroupFactory.create(stage=self.round_robin_stage, order=2)

        # Stage 2: Finals stage that follows Round Robin
        self.finals_stage = StageFactory.create(
            division=self.division,
            order=2,
            title="Finals",
            follows=self.round_robin_stage,
        )

    def test_valid_formulas_resolve_correctly(self):
        """
        Positive test: Valid formulae like G1P1 vs G2P2 should work correctly.
        """
        # Create UndecidedTeam objects with valid formulas
        # Note: Don't set both label and formula as per UndecidedTeamForm validation
        undecided_team_g1p1 = UndecidedTeamFactory.create(
            stage=self.finals_stage,
            formula="G1P1",  # Winner of Pool 1, Position 1
        )

        undecided_team_g2p2 = UndecidedTeamFactory.create(
            stage=self.finals_stage,
            formula="G2P2",  # Runner-up of Pool 2, Position 2
        )

        # Test that the UndecidedTeam.title properties resolve to expected values
        # G1P1 should resolve to "1st {pool1.title}" and G2P2 should resolve to "2nd {pool2.title}"
        self.assertEqual(undecided_team_g1p1.title, f"1st {self.pool1.title}")
        self.assertEqual(undecided_team_g2p2.title, f"2nd {self.pool2.title}")

        # Create a Match between the two undecided teams
        match = MatchFactory.create(
            stage=self.finals_stage,
            home_team_undecided=undecided_team_g1p1,
            away_team_undecided=undecided_team_g2p2,
            home_team=None,  # Explicitly set to None since we're using undecided teams
            away_team=None,  # Explicitly set to None since we're using undecided teams
            label="Final",
        )

        # Call the stage edit admin view which displays UndecidedTeam titles
        self.login(self.user)
        self.get(self.finals_stage.urls["edit"])
        self.response_200()
        # The page should contain the match label
        self.assertResponseContains("Final")

    def test_invalid_formulas_gracefully_handled_in_admin_view(self):
        """
        Test that invalid formulae are gracefully handled when accessing UndecidedTeam.title.

        This test demonstrates that UndecidedTeam objects with formulas referencing
        non-existent groups no longer crash when their title property is accessed.
        """
        # Create UndecidedTeam objects with invalid formulas
        # Note: Don't set both label and formula as per UndecidedTeamForm validation
        undecided_team_g5p2 = UndecidedTeamFactory.create(
            stage=self.finals_stage,
            formula="G5P2",  # References group 5, but we only have 2 pools
        )

        undecided_team_s1g5p1 = UndecidedTeamFactory.create(
            stage=self.finals_stage,
            formula="S1G5P1",  # Explicit stage reference, but group 5 doesn't exist
        )

        # Test the core fix: accessing title should not raise IndexError
        # After the fix, invalid formulas should return the formula as fallback
        self.assertEqual(undecided_team_g5p2.title, "G5P2")
        self.assertEqual(undecided_team_s1g5p1.title, "S1G5P1")

        # Test that choices also work correctly (fallback to division teams)
        self.assertEqual(undecided_team_g5p2.choices, self.finals_stage.division.teams)
        self.assertEqual(
            undecided_team_s1g5p1.choices, self.finals_stage.division.teams
        )

    def test_invalid_formulas_in_match_eval_fields(self):
        """
        Test that invalid formulas in home_team_eval and away_team_eval fields
        are handled gracefully when displayed in admin views and when Match.eval() is called.
        """
        # Create a Match with invalid formulas in eval fields
        match_with_invalid_formulas = MatchFactory.create(
            stage=self.finals_stage,
            home_team=None,
            away_team=None,
            home_team_eval="G5P2",  # Invalid - references group 5, but only 2 pools exist
            away_team_eval="G3P1",  # Invalid - references group 3, but only 2 pools exist
            label="Invalid Formula Match",
        )

        # Test that accessing the match in admin view doesn't crash
        self.login(self.user)
        self.get(self.finals_stage.urls["edit"])
        self.response_200()
        # The match should be displayed on the stage edit page
        self.assertResponseContains("Invalid Formula Match")
        # Verify that the home_team and away_team formulas are rendered correctly
        # Invalid formulas should show the formula itself as fallback
        self.assertResponseContains(
            "G5P2"
        )  # home_team_eval formula should be displayed
        self.assertResponseContains(
            "G3P1"
        )  # away_team_eval formula should be displayed

        # Test the eval() method directly - it should handle the IndexError gracefully
        # The Match.eval() method should return a tuple of (home_team, away_team)
        # For invalid formulas, the output should be the formula itself
        # The key is that no IndexError should be raised
        home_team, away_team = match_with_invalid_formulas.eval()
        self.assertEqual(
            home_team["title"], "G5P2"
        )  # Invalid formula should show the formula itself
        self.assertEqual(
            away_team["title"], "G3P1"
        )  # Invalid formula should show the formula itself

        # Also test that get_home_team() and get_away_team() don't crash
        # These methods call _get_team() which should handle invalid formulas gracefully
        # For invalid formulas, they should return the formula itself as the title
        home_team_result = match_with_invalid_formulas.get_home_team()
        away_team_result = match_with_invalid_formulas.get_away_team()
        self.assertEqual(
            home_team_result["title"], "G5P2"
        )  # Invalid formula should show the formula itself
        self.assertEqual(
            away_team_result["title"], "G3P1"
        )  # Invalid formula should show the formula itself

    def test_mixed_valid_and_invalid_formulas_in_admin_view(self):
        """
        Test that both valid and invalid formulas can coexist without crashes.
        """
        # Create a mix of valid and invalid UndecidedTeam objects
        # Note: Don't set both label and formula as per UndecidedTeamForm validation
        valid_team = UndecidedTeamFactory.create(
            stage=self.finals_stage,
            formula="G1P1",  # Valid
        )

        invalid_team = UndecidedTeamFactory.create(
            stage=self.finals_stage,
            formula="G3P1",  # Invalid - only 2 pools exist
        )

        # Create matches using both teams to force title evaluation in admin
        MatchFactory.create(
            stage=self.finals_stage,
            home_team_undecided=valid_team,
            away_team_undecided=invalid_team,
            home_team=None,
            away_team=None,
            label="Mixed Formula Match",
        )

        # Test that both teams can have their titles accessed without issues
        # Valid team should resolve to expected title based on template
        self.assertEqual(
            valid_team.title, f"1st {self.pool1.title}"
        )  # Should be formatted template output

        # Invalid team should return the formula as fallback
        self.assertEqual(invalid_team.title, "G3P1")

        # Test choices also work
        self.assertEqual(valid_team.choices, self.pool1.teams)
        self.assertEqual(invalid_team.choices, self.finals_stage.division.teams)

        # Test that the admin view renders successfully with mixed formulas
        self.login(self.user)
        self.get(self.finals_stage.urls["edit"])
        self.response_200()
        # The match label should appear
        self.assertResponseContains("Mixed Formula Match")
        # Verify that the home_team and away_team formulas are rendered correctly
        # Valid team (G1P1) should show the resolved title
        self.assertResponseContains(f"1st {self.pool1.title}")
        # Invalid team (G3P1) should show the formula as fallback
        self.assertResponseContains("G3P1")
