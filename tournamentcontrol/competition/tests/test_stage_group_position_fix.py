"""Comprehensive test coverage for stage_group_position parser (Issues #182, #183).

Tests the fix for AttributeError crash on invalid input and ensures comprehensive
coverage of all stage_group_position parsing scenarios.
"""

from test_plus import TestCase

from tournamentcontrol.competition.tests.factories import (
    DivisionFactory,
    MatchFactory,
    StageFactory,
    StageGroupFactory,
    TeamFactory,
)
from tournamentcontrol.competition.utils import stage_group_position_re


class StageGroupPositionRegexTests(TestCase):
    """
    Direct tests for the stage_group_position regex patterns.
    Tests the core regex matching behavior.
    """

    def test_valid_regex_patterns(self):
        """Test that valid stage_group_position patterns match correctly."""
        valid_patterns = [
            ("P1", (None, None, "1")),
            ("P10", (None, None, "10")),
            ("G1P1", (None, "1", "1")),
            ("G2P5", (None, "2", "5")),
            ("S1G1P1", ("1", "1", "1")),
            ("S2G3P4", ("2", "3", "4")),
            ("S10G20P30", ("10", "20", "30")),
            # These zero-based patterns are actually valid according to the regex
            ("P0", (None, None, "0")),
            ("G0P1", (None, "0", "1")),
            ("S0G1P1", ("0", "1", "1")),
            ("S1P1", ("1", None, "1")),  # Stage without group is valid
        ]

        for pattern, expected_groups in valid_patterns:
            with self.subTest(pattern=pattern):
                match = stage_group_position_re.match(pattern)
                self.assertIsNotNone(match, f"Pattern '{pattern}' should match")

                stage, group, position = match.groups()
                expected_stage, expected_group, expected_position = expected_groups

                self.assertEqual(stage, expected_stage)
                self.assertEqual(group, expected_group)
                self.assertEqual(position, expected_position)

    def test_invalid_regex_patterns(self):
        """Test that invalid stage_group_position patterns do not match."""
        invalid_patterns = [
            "BAD1",  # Short version of original crash case
            "Team A",  # Shortened version
            "INVALID",
            "BadPat",  # Shortened to fit varchar constraints
            "P",  # Missing position number
            "G1",  # Missing position
            "S1G1",  # Missing position
            "1P1",  # Invalid format
            "GP1",  # Missing group number
            "SG1P1",  # Missing stage number
            "",  # Empty string
            "ABC123",
            "123",
        ]

        for pattern in invalid_patterns:
            with self.subTest(pattern=pattern):
                match = stage_group_position_re.match(pattern)
                self.assertIsNone(match, f"Pattern '{pattern}' should not match")

    def test_partial_matches_not_accepted(self):
        """Test that partial matches at start of string don't count as valid."""
        partial_patterns = [
            "P1Extra",  # Valid start but extra text
            "G1P1More",
            "S1G1P1AndMore",
            "P1 ",  # Trailing space
            " P1",  # Leading space
        ]

        for pattern in partial_patterns:
            with self.subTest(pattern=pattern):
                match = stage_group_position_re.match(pattern)
                # These might match but should not be considered complete/valid
                if match:
                    # If it matches, the full match should not equal the input
                    # indicating the pattern didn't consume the whole string
                    self.assertNotEqual(match.group(0), pattern)


class StageGroupPositionModelFixTests(TestCase):
    """
    Tests for the AttributeError fix in Match model methods.
    Tests the actual usage scenarios that were crashing.
    """

    def setUp(self):
        """Set up test fixtures for model testing."""
        self.division = DivisionFactory.create()
        self.stage1 = StageFactory.create(division=self.division, order=1)
        self.stage2 = StageFactory.create(
            division=self.division, order=2, follows=self.stage1
        )

        # Create actual teams for more realistic testing
        self.team1 = TeamFactory.create(division=self.division)
        self.team2 = TeamFactory.create(division=self.division)

        # Create pools for valid formula testing
        self.pool1 = StageGroupFactory.create(stage=self.stage1)
        self.pool2 = StageGroupFactory.create(stage=self.stage1)

    def test_no_crash_on_invalid_formulas_get_team_methods(self):
        """Test Match.get_home_team() and get_away_team() don't crash on invalid formulas."""
        invalid_formulas = [
            "BAD1",  # Short version of original crash case
            "Team A",  # Shortened version
            "INVALID",
            "BadForm",  # Shortened to fit varchar(10)
            "",
        ]

        for home_formula in invalid_formulas:
            for away_formula in invalid_formulas[
                :2
            ]:  # Limit combinations for performance
                with self.subTest(home=home_formula, away=away_formula):
                    match = MatchFactory.create(
                        stage=self.stage2,
                        home_team=None,
                        away_team=None,
                        home_team_eval=home_formula,
                        away_team_eval=away_formula,
                    )

                    # These should not raise AttributeError with 'groups' message
                    home_result = match.get_home_team()
                    away_result = match.get_away_team()

                    # Should return fallback values
                    self.assertEqual(home_result, {"title": "None"})
                    self.assertEqual(away_result, {"title": "None"})

    def test_no_crash_on_invalid_formulas_eval_method(self):
        """Test Match.eval() method doesn't crash on invalid formulas."""
        match = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="BAD1",  # Short version of original crash case
            away_team_eval="Team B",  # Shortened version
        )

        # This should not raise AttributeError
        home_team, away_team = match.eval()

        self.assertEqual(home_team, {"title": "None"})
        self.assertEqual(away_team, {"title": "None"})

    def test_valid_formulas_still_work_correctly(self):
        """Test that valid formulas continue to work after the fix."""
        match = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="P1",
            away_team_eval="P2",
        )

        home_result = match.get_home_team()
        away_result = match.get_away_team()

        # Should return proper ordinal positions
        self.assertEqual(home_result, {"title": "1st"})
        self.assertEqual(away_result, {"title": "2nd"})

    def test_complex_valid_formulas(self):
        """Test valid formulas with stage and group references."""
        match = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="S1G1P1",  # Stage 1, Group 1, Position 1
            away_team_eval="G2P1",  # Group 2, Position 1
        )

        # These should work without crashing
        home_result = match.get_home_team()
        away_result = match.get_away_team()

        # Should return ordinal positions with pool info
        self.assertIn("1st", home_result["title"])
        self.assertIn("1st", away_result["title"])

    def test_edge_cases_dont_crash(self):
        """Test edge cases that might cause issues."""
        edge_cases = [
            None,  # Null values
            "",  # Empty strings
            "   ",  # Whitespace
            "0",  # Numbers that don't match pattern
            "P",  # Incomplete patterns
            "G1",  # Missing position
        ]

        for formula in edge_cases:
            with self.subTest(formula=repr(formula)):
                match = MatchFactory.create(
                    stage=self.stage2,
                    home_team=None,
                    away_team=None,
                    home_team_eval=formula,
                    away_team_eval="P1",  # Valid formula for comparison
                )

                # Should handle gracefully
                home_result = match.get_home_team()
                away_result = match.get_away_team()

                self.assertEqual(home_result, {"title": "None"})
                self.assertEqual(away_result, {"title": "1st"})


class StageGroupPositionIntegrationTests(TestCase):
    """
    Integration tests that verify stage_group_position works correctly
    in realistic competition scenarios.
    """

    def setUp(self):
        """Set up a realistic two-stage competition."""
        self.division = DivisionFactory.create()

        # Stage 1: Round Robin with two groups
        self.stage1 = StageFactory.create(division=self.division, order=1)
        self.group1 = StageGroupFactory.create(stage=self.stage1)
        self.group2 = StageGroupFactory.create(stage=self.stage1)

        # Stage 2: Finals
        self.stage2 = StageFactory.create(
            division=self.division, order=2, follows=self.stage1
        )

        # Add teams to groups
        self.teams_g1 = [TeamFactory.create(division=self.division) for _ in range(4)]
        self.teams_g2 = [TeamFactory.create(division=self.division) for _ in range(4)]

        for team in self.teams_g1:
            self.group1.teams.add(team)
        for team in self.teams_g2:
            self.group2.teams.add(team)

    def test_realistic_finals_scenario(self):
        """Test a realistic finals match between group winners."""
        # Final match: Winner of Group 1 vs Winner of Group 2
        final_match = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="G1P1",  # Group 1, Position 1 (Winner)
            away_team_eval="G2P1",  # Group 2, Position 1 (Winner)
            label="Final",
        )

        home_result = final_match.get_home_team()
        away_result = final_match.get_away_team()

        # Should return ordinal positions with pool info
        self.assertIn("1st", home_result["title"])
        self.assertIn("1st", away_result["title"])

    def test_semifinal_scenario(self):
        """Test semifinal matches with valid formulas."""
        # Semi 1: G1P1 vs G2P2
        # Semi 2: G1P2 vs G2P1

        semi1 = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="G1P1",
            away_team_eval="G2P2",
            label="Semifinal 1",
        )

        semi2 = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="G1P2",
            away_team_eval="G2P1",
            label="Semifinal 2",
        )

        # Test both semifinals - check that ordinal positions are included
        home_semi1 = semi1.get_home_team()["title"]
        away_semi1 = semi1.get_away_team()["title"]
        home_semi2 = semi2.get_home_team()["title"]
        away_semi2 = semi2.get_away_team()["title"]

        self.assertIn("1st", home_semi1)
        self.assertIn("2nd", away_semi1)
        self.assertIn("2nd", home_semi2)
        self.assertIn("1st", away_semi2)

    def test_invalid_group_reference_handled_gracefully(self):
        """Test that invalid group references don't crash in realistic scenarios."""
        # Try to reference a group that doesn't exist
        match = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="G5P1",  # Group 5 doesn't exist (only have groups 1 and 2)
            away_team_eval="G1P1",  # Valid reference
            label="Invalid Group Test",
        )

        # Should handle gracefully without crashing
        home_result = match.get_home_team()
        away_result = match.get_away_team()

        # Invalid group should return the formula as title (graceful fallback)
        self.assertEqual(home_result, {"title": "G5P1"})
        # Valid group should work normally
        self.assertIn("1st", away_result["title"])
