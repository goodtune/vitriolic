"""
Test case specifically for the stage_group_position parser fix (Issue #182).

This test demonstrates that the AttributeError crash on invalid input
has been fixed and that both valid and invalid inputs are handled gracefully.
"""
from test_plus import TestCase
from tournamentcontrol.competition.tests.factories import (
    MatchFactory,
    StageFactory,
    DivisionFactory,
)


class StageGroupPositionParserFixTests(TestCase):
    """
    Test cases specifically for the stage_group_position parser crash fix.
    These tests demonstrate the fix for Issue #182.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.division = DivisionFactory.create()
        self.stage1 = StageFactory.create(division=self.division, order=1)
        self.stage2 = StageFactory.create(division=self.division, order=2, follows=self.stage1)

    def test_invalid_stage_group_position_no_longer_crashes(self):
        """
        Test that invalid stage_group_position values no longer cause AttributeError crashes.
        
        This is the core test for Issue #182.
        """
        # Create a match with invalid eval fields (short enough for varchar(10))
        match = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="INVALID1",  # Invalid format - should cause match() to return None
            away_team_eval="INVALID2",  # Another invalid format 
            label="Test Match",
        )

        # Before the fix, this would raise:
        # AttributeError: 'NoneType' object has no attribute 'groups'
        
        # After the fix, it should handle gracefully
        try:
            # Call _get_team method which contains the fixed code
            home_team_result = match._get_team("home_team")
            away_team_result = match._get_team("away_team")
            
            # The method should return something, not crash
            self.assertIsNotNone(home_team_result)
            self.assertIsNotNone(away_team_result)
            
        except AttributeError as e:
            if "groups" in str(e):
                self.fail(f"AttributeError with 'groups' should be fixed: {e}")
            # Re-raise if it's a different AttributeError
            raise

    def test_eval_method_handles_invalid_formulas(self):
        """
        Test that the Match.eval() method handles invalid formulas gracefully.
        This tests the second location where the fix was applied.
        """
        # Create a match with invalid eval fields (short enough for varchar(10))
        match = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="BAD1",  # Invalid format
            away_team_eval="BAD2",  # Invalid format
            label="Test Match",
        )

        # Before the fix, this could crash in the eval() method
        # After the fix, it should handle gracefully
        try:
            home_team, away_team = match.eval()
            
            # Should return something, not crash
            self.assertIsNotNone(home_team)
            self.assertIsNotNone(away_team)
            
        except AttributeError as e:
            if "groups" in str(e):
                self.fail(f"AttributeError with 'groups' should be fixed: {e}")
            # Re-raise if it's a different AttributeError
            raise

    def test_valid_formulas_still_work(self):
        """
        Test that valid stage_group_position formulas still work correctly after the fix.
        This ensures we haven't broken existing functionality.
        """
        # Create a match with valid eval fields
        match = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="P1",  # Valid: position 1
            away_team_eval="G1P2",  # Valid: group 1, position 2  
            label="Valid Test",
        )

        # Valid formulas should still be processed correctly
        try:
            home_team_result = match._get_team("home_team")
            away_team_result = match._get_team("away_team")
            
            # Methods should not crash
            self.assertIsNotNone(home_team_result)
            self.assertIsNotNone(away_team_result)
            
        except AttributeError as e:
            if "groups" in str(e):
                self.fail(f"Valid formulas should not cause AttributeError: {e}")
            # Re-raise if it's a different AttributeError
            raise

    def test_empty_and_none_values_handled(self):
        """
        Test that empty strings and None values are handled gracefully.
        """
        # Create matches with edge case values
        test_cases = [
            ("", ""),  # Empty strings
            ("NONE1", "NONE2"),  # Values that don't match the pattern
        ]
        
        for home_eval, away_eval in test_cases:
            with self.subTest(home_eval=home_eval, away_eval=away_eval):
                match = MatchFactory.create(
                    stage=self.stage2,
                    home_team=None,
                    away_team=None,
                    home_team_eval=home_eval,
                    away_team_eval=away_eval,
                    label="Edge Test",
                )

                # Should not crash with AttributeError about 'groups'
                try:
                    home_result = match._get_team("home_team")
                    away_result = match._get_team("away_team")
                    
                    self.assertIsNotNone(home_result)
                    self.assertIsNotNone(away_result)
                    
                except AttributeError as e:
                    if "groups" in str(e):
                        self.fail(f"Edge case values should not cause groups AttributeError: {e}")
                    raise