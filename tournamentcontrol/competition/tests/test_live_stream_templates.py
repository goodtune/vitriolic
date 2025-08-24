"""
Test for live stream template rendering functionality.
"""

from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from tournamentcontrol.competition.tests import factories


class LiveStreamTemplateTest(TestCase):
    """Test that live stream templates render correctly."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_live_stream_title_template_rendering(self):
        """Test that the live stream title template renders correctly."""
        # Create test objects
        stage = factories.StageFactory.create()
        competition = stage.division.season.competition
        season = stage.division.season
        division = stage.division

        ground = factories.GroundFactory.create(venue__season=season)
        match = factories.MatchFactory.create(
            stage=stage, play_at=ground, label="Semi Final"
        )

        # Create context for template rendering
        context = {
            "match": match,
            "competition": competition,
            "season": season,
            "division": division,
            "stage": stage,
            "match_url": "http://example.com/match/123/",
        }

        # Render the title template
        title = render_to_string(
            "tournamentcontrol/competition/match/live_stream/title.txt", context
        ).strip()

        # Verify exact expected output
        expected_title = (
            f"{division.title} | Semi Final: "
            f"{match.get_home_team_plain()} vs {match.get_away_team_plain()} | "
            f"{competition.title} {season.title}"
        )
        self.assertEqual(title, expected_title)

    def test_live_stream_description_template_rendering(self):
        """Test that the live stream description template renders correctly."""
        # Create test objects
        stage = factories.StageFactory.create()
        competition = stage.division.season.competition
        season = stage.division.season
        division = stage.division

        ground = factories.GroundFactory.create(venue__season=season)
        match = factories.MatchFactory.create(stage=stage, play_at=ground)

        # Create context for template rendering
        context = {
            "match": match,
            "competition": competition,
            "season": season,
            "division": division,
            "stage": stage,
            "match_url": "http://example.com/match/123/",
        }

        # Render the description template
        description = render_to_string(
            "tournamentcontrol/competition/match/live_stream/description.txt", context
        ).strip()

        # Verify exact expected output
        expected_description = (
            f"Live stream of the {division.title} division of {competition.title} {season.title} "
            f"from {match.play_at.ground.venue}.\n\n"
            f"Watch {match.get_home_team_plain()} take on {match.get_away_team_plain()} "
            f"on {match.play_at}.\n\n"
            f"Full match details are available at http://example.com/match/123/\n\n"
            f"Subscribe to receive notifications of upcoming matches."
        )
        self.assertEqual(description, expected_description)

    def test_live_stream_title_without_label(self):
        """Test title template with a match that has no label."""
        # Create test objects
        stage = factories.StageFactory.create()
        competition = stage.division.season.competition
        season = stage.division.season
        division = stage.division

        ground = factories.GroundFactory.create(venue__season=season)
        match = factories.MatchFactory.create(
            stage=stage, play_at=ground, label=""  # No label
        )

        # Create context for template rendering
        context = {
            "match": match,
            "competition": competition,
            "season": season,
            "division": division,
            "stage": stage,
            "match_url": "http://example.com/match/123/",
        }

        # Render the title template
        title = render_to_string(
            "tournamentcontrol/competition/match/live_stream/title.txt", context
        ).strip()

        # Verify exact expected output without label
        expected_title = (
            f"{division.title} | "
            f"{match.get_home_team_plain()} vs {match.get_away_team_plain()} | "
            f"{competition.title} {season.title}"
        )
        self.assertEqual(title, expected_title)

    def test_live_stream_title_with_null_label(self):
        """Test title template with a match that has null label."""
        # Create test objects
        stage = factories.StageFactory.create()
        competition = stage.division.season.competition
        season = stage.division.season
        division = stage.division

        ground = factories.GroundFactory.create(venue__season=season)
        match = factories.MatchFactory.create(
            stage=stage, play_at=ground, label=None  # Null label
        )

        # Create context for template rendering
        context = {
            "match": match,
            "competition": competition,
            "season": season,
            "division": division,
            "stage": stage,
            "match_url": "http://example.com/match/123/",
        }

        # Render the title template
        title = render_to_string(
            "tournamentcontrol/competition/match/live_stream/title.txt", context
        ).strip()

        # Verify exact expected output without label
        expected_title = (
            f"{division.title} | "
            f"{match.get_home_team_plain()} vs {match.get_away_team_plain()} | "
            f"{competition.title} {season.title}"
        )
        self.assertEqual(title, expected_title)

    def test_custom_template_hierarchy_override(self):
        """Test that custom templates in the hierarchy work correctly."""
        # Create test objects with specific names to match our test template
        competition = factories.CompetitionFactory.create(slug="test-comp")
        season = factories.SeasonFactory.create(competition=competition, slug="2024")
        division = factories.DivisionFactory.create(season=season, slug="div1")
        stage = factories.StageFactory.create(division=division)

        ground = factories.GroundFactory.create(venue__season=season)
        match = factories.MatchFactory.create(
            stage=stage, play_at=ground, label="Championship"
        )

        # Create context for template rendering
        context = {
            "match": match,
            "competition": competition,
            "season": season,
            "division": division,
            "stage": stage,
            "match_url": "http://example.com/match/123/",
        }

        # Test that the custom template hierarchy pattern works
        # The custom template should be in tests/example_app/templates/
        title = render_to_string(
            "tournamentcontrol/competition/test-comp/2024/div1/match/live_stream/title.txt",
            context,
        ).strip()

        # Verify the custom template is used (with trophy emoji)
        expected_title = (
            f"🏆 {division.title} Championship | Championship: "
            f"{match.get_home_team_plain()} vs {match.get_away_team_plain()} | "
            f"{competition.title} {season.title}"
        )
        self.assertEqual(title, expected_title)

    def test_template_context_variables(self):
        """Test that all expected context variables are available to templates."""
        # Create test objects
        stage = factories.StageFactory.create()
        competition = stage.division.season.competition
        season = stage.division.season
        division = stage.division

        ground = factories.GroundFactory.create(venue__season=season)
        match = factories.MatchFactory.create(stage=stage, play_at=ground)

        # Create context for template rendering
        context = {
            "match": match,
            "competition": competition,
            "season": season,
            "division": division,
            "stage": stage,
            "match_url": "http://example.com/match/123/",
        }

        # Test a simple template that uses all context variables
        test_template = (
            "{{ match.id }}-{{ competition.slug }}-{{ season.slug }}-"
            "{{ division.slug }}-{{ stage.slug }}-{{ match_url }}"
        )

        from django.template import Context, Template

        template = Template(test_template)
        result = template.render(Context(context))

        expected_result = (
            f"{match.id}-{competition.slug}-{season.slug}-"
            f"{division.slug}-{stage.slug}-http://example.com/match/123/"
        )
        self.assertEqual(result, expected_result)
