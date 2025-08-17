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

        # Verify title contains expected elements
        self.assertIn(division.title, title)
        self.assertIn("Semi Final", title)  # The match label
        self.assertIn(str(match.get_home_team_plain()), title)
        self.assertIn(str(match.get_away_team_plain()), title)
        self.assertIn(competition.title, title)
        self.assertIn(season.title, title)

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

        # Verify description contains expected elements
        self.assertIn("Live stream of the", description)
        self.assertIn(division.title, description)
        self.assertIn(competition.title, description)
        self.assertIn(season.title, description)
        self.assertIn(str(match.get_home_team_plain()), description)
        self.assertIn(str(match.get_away_team_plain()), description)
        self.assertIn("http://example.com/match/123/", description)
        self.assertIn("Subscribe to receive notifications", description)

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

        # Verify title doesn't contain empty label but has other elements
        self.assertNotIn(": vs", title)  # Should not have ": " from empty label
        self.assertIn(division.title, title)
        self.assertIn(str(match.get_home_team_plain()), title)
        self.assertIn(str(match.get_away_team_plain()), title)
        self.assertIn(competition.title, title)
        self.assertIn(season.title, title)
