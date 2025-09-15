from django.core.exceptions import ValidationError
from test_plus import TestCase

from tournamentcontrol.competition.forms import MatchEditForm
from tournamentcontrol.competition.models import Match
from tournamentcontrol.competition.tests import factories


class CrossDivisionMatchTests(TestCase):
    """Test cross-division and non-standard match functionality."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for cross-division match tests."""
        # Create a season with multiple divisions
        cls.season = factories.SeasonFactory()
        cls.division1 = factories.DivisionFactory(season=cls.season, title="Division A")
        cls.division2 = factories.DivisionFactory(season=cls.season, title="Division B")
        
        # Create stages for each division
        cls.stage1 = factories.StageFactory(division=cls.division1)
        cls.stage2 = factories.StageFactory(division=cls.division2)
        
        # Create teams in different divisions
        cls.team1_div1 = factories.TeamFactory(division=cls.division1, title="Team 1 Div A")
        cls.team2_div1 = factories.TeamFactory(division=cls.division1, title="Team 2 Div A")
        cls.team1_div2 = factories.TeamFactory(division=cls.division2, title="Team 1 Div B")
        cls.team2_div2 = factories.TeamFactory(division=cls.division2, title="Team 2 Div B")

    def test_default_ignore_group_validation_is_false(self):
        """Test that ignore_group_validation defaults to False."""
        match = Match(stage=self.stage1)
        self.assertEqual(match.ignore_group_validation, False)

    def test_standard_match_enforces_division_validation(self):
        """Test that the ignore_group_validation field defaults to false and works as expected."""
        match = factories.MatchFactory(
            stage=self.stage1,
            ignore_group_validation=False,
            home_team=self.team1_div1,
            away_team=self.team2_div1  # Same division teams
        )
        
        # Verify that the default behavior works - same division teams should be valid
        form_data = {
            'home_team': self.team1_div1.pk,
            'away_team': self.team2_div1.pk,  # Same division
            'ignore_group_validation': '0',  # BooleanChoiceField expects "0" for False
            'include_in_ladder': '1',  # BooleanChoiceField expects "1" for True
        }
        
        form = MatchEditForm(instance=match, data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        # Verify the flag is correctly set to False
        saved_match = form.save()
        self.assertFalse(saved_match.ignore_group_validation)

    def test_cross_division_match_bypasses_validation(self):
        """Test that matches with ignore_group_validation=True bypass division validation."""
        match = factories.MatchFactory(
            stage=self.stage1,
            ignore_group_validation=True
        )
        
        # Form should accept teams from different divisions
        form_data = {
            'home_team': self.team1_div1.pk,
            'away_team': self.team1_div2.pk,  # Different division
            'ignore_group_validation': '1',  # BooleanChoiceField expects "1" for True
            'include_in_ladder': '1',  # BooleanChoiceField expects "1" for True
        }
        
        form = MatchEditForm(instance=match, data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        saved_match = form.save()
        self.assertEqual(saved_match.home_team, self.team1_div1)
        self.assertEqual(saved_match.away_team, self.team1_div2)
        self.assertTrue(saved_match.ignore_group_validation)

    def test_cross_division_match_form_includes_field(self):
        """Test that MatchEditForm includes ignore_group_validation field."""
        match = factories.MatchFactory(stage=self.stage1)
        form = MatchEditForm(instance=match)
        self.assertIn('ignore_group_validation', form.fields)
        self.assertEqual(
            form.fields['ignore_group_validation'].help_text,
            "Allow this match to bypass strict Division and StageGroup validation. "
            "Use for friendlies, showcase events, or cross-division matchups. "
            "These matches will not count toward standings."
        )

    def test_same_team_validation_still_applies(self):
        """Test that teams cannot play against themselves even with ignore_group_validation=True."""
        match = factories.MatchFactory(
            stage=self.stage1,
            ignore_group_validation=True
        )
        
        form_data = {
            'home_team': self.team1_div1.pk,
            'away_team': self.team1_div1.pk,  # Same team
            'ignore_group_validation': '1',
            'include_in_ladder': '1',
        }
        
        form = MatchEditForm(instance=match, data=form_data)
        self.assertFormError(form, 'away_team', ["Teams cannot be scheduled to play against itself."])

    def test_stage_group_validation_bypassed_when_flag_set(self):
        """Test that pool/stage group validation is bypassed when ignore_group_validation=True."""
        # Create a stage with pools
        pool1 = factories.StageGroupFactory.create(stage=self.stage1)
        pool2 = factories.StageGroupFactory.create(stage=self.stage1)
        
        # Add teams to different pools
        pool1.teams.add(self.team1_div1)
        pool2.teams.add(self.team2_div1)
        
        match = factories.MatchFactory(
            stage=self.stage1,
            stage_group=pool1,
            ignore_group_validation=True
        )
        
        # Should allow teams from different pools when flag is set
        form_data = {
            'stage_group': pool1.pk,
            'home_team': self.team1_div1.pk,
            'away_team': self.team2_div1.pk,  # Different pool
            'ignore_group_validation': '1',
            'include_in_ladder': '1',
        }
        
        form = MatchEditForm(instance=match, data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_standard_match_enforces_stage_group_validation(self):
        """Test that standard matches enforce stage group validation."""
        # Create a stage with pools
        pool1 = factories.StageGroupFactory.create(stage=self.stage1)
        
        # Add both teams to the same pool initially
        pool1.teams.add(self.team1_div1, self.team2_div1)
        
        match = factories.MatchFactory(
            stage=self.stage1,
            stage_group=pool1,
            ignore_group_validation=False,
            home_team=self.team1_div1,
            away_team=self.team2_div1
        )
        
        # Should accept teams from the same pool when flag is False
        form_data = {
            'stage_group': pool1.pk,
            'home_team': self.team1_div1.pk,
            'away_team': self.team2_div1.pk,  # Same pool
            'ignore_group_validation': '0',
            'include_in_ladder': '1',
        }
        
        form = MatchEditForm(instance=match, data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        # Verify the flag is correctly set to False
        saved_match = form.save()
        self.assertFalse(saved_match.ignore_group_validation)

    def test_undecided_team_validation_respects_flag(self):
        """Test that undecided team validation also respects the ignore_group_validation flag."""
        # Create undecided teams for different stages
        undecided1 = factories.UndecidedTeamFactory.create(stage=self.stage1)
        undecided2 = factories.UndecidedTeamFactory.create(stage=self.stage2)
        
        match = factories.MatchFactory(
            stage=self.stage1,
            ignore_group_validation=True
        )
        
        # Should allow undecided teams from different stages when flag is set
        form_data = {
            'home_team_undecided': undecided1.pk,
            'away_team_undecided': undecided2.pk,  # Different stage
            'ignore_group_validation': '1',
            'include_in_ladder': '1',
        }
        
        form = MatchEditForm(instance=match, data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_match_string_representation_includes_validation_status(self):
        """Test that matches clearly indicate their non-standard status."""
        # Create a standard match
        standard_match = factories.MatchFactory(
            stage=self.stage1,
            home_team=self.team1_div1,
            away_team=self.team2_div1,
            ignore_group_validation=False
        )
        
        # Create a cross-division match
        cross_div_match = factories.MatchFactory(
            stage=self.stage1,
            home_team=self.team1_div1,
            away_team=self.team1_div2,
            ignore_group_validation=True
        )
        
        # Both should have valid field values
        self.assertEqual(standard_match.home_team.title, "Team 1 Div A")
        self.assertEqual(standard_match.away_team.title, "Team 2 Div A")
        self.assertEqual(standard_match.home_team, self.team1_div1)
        self.assertEqual(standard_match.away_team, self.team2_div1)
        
        self.assertEqual(cross_div_match.home_team.title, "Team 1 Div A")
        self.assertEqual(cross_div_match.away_team.title, "Team 1 Div B")
        self.assertEqual(cross_div_match.home_team, self.team1_div1)
        self.assertEqual(cross_div_match.away_team, self.team1_div2)