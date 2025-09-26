"""
Test for live stream template rendering functionality.
"""

from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from tournamentcontrol.competition.tests import factories


class LiveStreamTemplateTest(TestCase):
    """Test that live stream templates render correctly."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create common test objects that can be reused across tests
        cls.stage = factories.StageFactory.create()
        cls.competition = cls.stage.division.season.competition
        cls.season = cls.stage.division.season
        cls.division = cls.stage.division
        cls.ground = factories.GroundFactory.create(venue__season=cls.season)

        # Create matches with different labels for testing
        cls.match_with_label = factories.MatchFactory.create(
            stage=cls.stage, play_at=cls.ground, label="Semi Final"
        )
        cls.match_without_label = factories.MatchFactory.create(
            stage=cls.stage, play_at=cls.ground, label=""
        )
        cls.match_null_label = factories.MatchFactory.create(
            stage=cls.stage, play_at=cls.ground, label=None
        )

        # Create custom hierarchy objects for testing overrides
        cls.custom_competition = factories.CompetitionFactory.create(slug="test-comp")
        cls.custom_season = factories.SeasonFactory.create(
            competition=cls.custom_competition, slug="2024"
        )
        cls.custom_division = factories.DivisionFactory.create(
            season=cls.custom_season, slug="div1"
        )
        cls.custom_stage = factories.StageFactory.create(division=cls.custom_division)
        cls.custom_ground = factories.GroundFactory.create(
            venue__season=cls.custom_season
        )
        cls.custom_match = factories.MatchFactory.create(
            stage=cls.custom_stage, play_at=cls.custom_ground, label="Championship"
        )

    def setUp(self):
        self.factory = RequestFactory()

    def _get_template_context(self, match=None):
        """Helper method to create template context."""
        if match is None:
            match = self.match_with_label

        return {
            "match": match,
            "competition": match.stage.division.season.competition,
            "season": match.stage.division.season,
            "division": match.stage.division,
            "stage": match.stage,
            "match_url": "http://example.com/match/123/",
        }

    def test_live_stream_title_template_rendering(self):
        """Test that the live stream title template renders correctly."""
        context = self._get_template_context(self.match_with_label)

        # Render the title template
        title = render_to_string(
            "tournamentcontrol/competition/match/live_stream/title.txt", context
        ).strip()

        # Verify exact expected output
        expected_title = (
            f"{self.division.title} | Semi Final: "
            f"{self.match_with_label.get_home_team_plain()} vs {self.match_with_label.get_away_team_plain()} | "
            f"{self.competition.title} {self.season.title}"
        )
        self.assertEqual(title, expected_title)

    def test_live_stream_description_template_rendering(self):
        """Test that the live stream description template renders correctly."""
        context = self._get_template_context(self.match_with_label)

        # Render the description template
        description = render_to_string(
            "tournamentcontrol/competition/match/live_stream/description.txt", context
        ).strip()

        # Verify exact expected output
        expected_description = (
            f"Live stream of the {self.division.title} division of {self.competition.title} {self.season.title} "
            f"from {self.match_with_label.play_at.ground.venue}.\n\n"
            f"Watch {self.match_with_label.get_home_team_plain()} take on {self.match_with_label.get_away_team_plain()} "
            f"on {self.match_with_label.play_at}.\n\n"
            f"Full match details are available at http://example.com/match/123/\n\n"
            f"Subscribe to receive notifications of upcoming matches."
        )
        self.assertEqual(description, expected_description)

    def test_live_stream_title_without_label(self):
        """Test title template with a match that has no label."""
        context = self._get_template_context(self.match_without_label)

        # Render the title template
        title = render_to_string(
            "tournamentcontrol/competition/match/live_stream/title.txt", context
        ).strip()

        # Verify exact expected output without label
        expected_title = (
            f"{self.division.title} | "
            f"{self.match_without_label.get_home_team_plain()} vs {self.match_without_label.get_away_team_plain()} | "
            f"{self.competition.title} {self.season.title}"
        )
        self.assertEqual(title, expected_title)

    def test_live_stream_title_with_null_label(self):
        """Test title template with a match that has null label."""
        context = self._get_template_context(self.match_null_label)

        # Render the title template
        title = render_to_string(
            "tournamentcontrol/competition/match/live_stream/title.txt", context
        ).strip()

        # Verify exact expected output without label
        expected_title = (
            f"{self.division.title} | "
            f"{self.match_null_label.get_home_team_plain()} vs {self.match_null_label.get_away_team_plain()} | "
            f"{self.competition.title} {self.season.title}"
        )
        self.assertEqual(title, expected_title)

    def test_custom_template_hierarchy_override(self):
        """Test that custom templates in the hierarchy work correctly."""
        context = self._get_template_context(self.custom_match)

        # Test that the custom template hierarchy pattern works
        # The custom template should be in tests/example_app/templates/
        title = render_to_string(
            "tournamentcontrol/competition/test-comp/2024/div1/match/live_stream/title.txt",
            context,
        ).strip()

        # Verify the custom template is used (with trophy emoji)
        expected_title = (
            f"🏆 {self.custom_division.title} Championship | Championship: "
            f"{self.custom_match.get_home_team_plain()} vs {self.custom_match.get_away_team_plain()} | "
            f"{self.custom_competition.title} {self.custom_season.title}"
        )
        self.assertEqual(title, expected_title)

    def test_template_context_variables(self):
        """Test that all expected context variables are available to templates."""
        context = self._get_template_context(self.match_with_label)

        # Test a simple template that uses all context variables
        test_template = (
            "{{ match.id }}-{{ competition.slug }}-{{ season.slug }}-"
            "{{ division.slug }}-{{ stage.slug }}-{{ match_url }}"
        )

        template = Template(test_template)
        result = template.render(Context(context))

        expected_result = (
            f"{self.match_with_label.id}-{self.competition.slug}-{self.season.slug}-"
            f"{self.division.slug}-{self.stage.slug}-http://example.com/match/123/"
        )
        self.assertEqual(result, expected_result)
