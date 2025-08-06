# -*- coding: utf-8 -*-

from test_plus import TestCase

from tournamentcontrol.competition.ai import AICompetitionService, CompetitionPlan
from tournamentcontrol.competition.models import Competition, Season


class AICompetitionServiceTestCase(TestCase):
    """Test the AI Competition Service functionality."""

    def test_service_initialization(self):
        """Test that the service can be initialized."""
        service = AICompetitionService()
        self.assertIsNotNone(service)
        self.assertFalse(service.is_available())  # No API key configured

    def test_mock_plan_generation(self):
        """Test that mock plans are generated correctly."""
        service = AICompetitionService()

        prompt = "Build a competition for 16 teams over 4 days"
        plan = service.generate_plan(prompt)

        self.assertIsInstance(plan, CompetitionPlan)
        self.assertEqual(plan.total_teams, 16)
        self.assertEqual(plan.total_days, 4)
        self.assertTrue(len(plan.divisions) > 0)
        self.assertIn("mock", plan.warnings[0].lower())

    def test_plan_structure(self):
        """Test that generated plans have the correct structure."""
        service = AICompetitionService()

        plan = service.generate_plan("8 teams, 3 days")

        # Check overall structure
        self.assertEqual(plan.total_teams, 8)
        self.assertEqual(plan.total_days, 3)

        # Check division structure
        self.assertEqual(len(plan.divisions), 1)
        division = plan.divisions[0]
        self.assertEqual(division.team_count, 8)
        self.assertEqual(len(division.teams), 8)

        # Check stage structure
        self.assertTrue(len(division.stages) >= 1)
        stage = division.stages[0]
        self.assertIn(stage.stage_type, ["round_robin", "knockout", "swiss"])
        self.assertTrue(len(stage.pools) > 0)

    def test_team_name_generation(self):
        """Test that team names are generated correctly."""
        service = AICompetitionService()

        plan = service.generate_plan("5 teams")
        division = plan.divisions[0]

        self.assertEqual(len(division.teams), 5)
        for i, team_name in enumerate(division.teams):
            self.assertEqual(team_name, f"Team {i+1}")

    def test_plan_with_different_team_counts(self):
        """Test plans with various team counts."""
        service = AICompetitionService()

        test_cases = [4, 8, 16, 19, 32]

        for team_count in test_cases:
            with self.subTest(teams=team_count):
                plan = service.generate_plan(f"{team_count} teams")
                self.assertEqual(plan.total_teams, team_count)
                self.assertEqual(len(plan.divisions[0].teams), team_count)


class AICompetitionWizardTestCase(TestCase):
    """Test the AI Competition Wizard forms."""

    def test_prompt_form_validation(self):
        """Test that the prompt form validates correctly."""
        from tournamentcontrol.competition.wizards import AIPromptForm

        # Valid form
        form_data = {
            "prompt": "Build a competition for 8 teams over 3 days",
            "include_existing_teams": False,
        }
        form = AIPromptForm(data=form_data)
        self.assertTrue(form.is_valid())

        # Invalid form - empty prompt
        form_data = {"prompt": "", "include_existing_teams": False}
        form = AIPromptForm(data=form_data)
        self.assertFalse(form.is_valid())

    def test_plan_review_form(self):
        """Test the plan review form."""
        from tournamentcontrol.competition.wizards import AIPlanReviewForm
        from tournamentcontrol.competition.ai import (
            CompetitionPlan,
            DivisionStructure,
            StageStructure,
            PoolStructure,
        )

        # Create a test plan
        pool = PoolStructure(
            name="Pool A", teams=["Team 1", "Team 2"], description="Test pool"
        )
        stage = StageStructure(
            name="Round Robin", stage_type="round_robin", pools=[pool]
        )
        division = DivisionStructure(
            name="Test Division",
            team_count=2,
            teams=["Team 1", "Team 2"],
            stages=[stage],
        )
        plan = CompetitionPlan(
            description="Test plan", total_teams=2, total_days=1, divisions=[division]
        )

        # Test form with plan
        form = AIPlanReviewForm(plan=plan)
        self.assertIsNotNone(form.plan)
        self.assertEqual(form.plan.total_teams, 2)

        # Test form validation
        import json
        from dataclasses import asdict
        
        form_data = {
            "approve_plan": True,
            "plan_data": json.dumps(asdict(plan)),
        }
        form = AIPlanReviewForm(plan=plan, data=form_data)
        self.assertTrue(form.is_valid())

        # Test without approval
        form_data = {
            "approve_plan": False,
            "plan_data": json.dumps(asdict(plan)),
        }
        form = AIPlanReviewForm(plan=plan, data=form_data)
        self.assertFalse(form.is_valid())
