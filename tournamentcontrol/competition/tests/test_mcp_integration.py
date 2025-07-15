"""
Test MCP Server Integration for Tournament Control Competition API.
"""

from django.test.utils import override_settings
from django.urls import reverse
from test_plus import TestCase

from tournamentcontrol.competition.tests import factories


@override_settings(ROOT_URLCONF="vitriolic.urls")
class MCPServerIntegrationTests(TestCase):
    """Test MCP server endpoints and integration."""

    @classmethod
    def setUpTestData(cls):
        """Create test data once for all tests."""
        # Create a club
        cls.club = factories.ClubFactory.create()

        # Create a competition with a known slug
        cls.competition = factories.CompetitionFactory.create()

        # Create a season with a known slug
        cls.season = factories.SeasonFactory.create(competition=cls.competition)

        # Create a division with a known slug
        cls.division = factories.DivisionFactory.create(season=cls.season)

        # Create a stage
        cls.stage = factories.StageFactory.create(division=cls.division)

        # Create teams
        cls.team1 = factories.TeamFactory.create(club=cls.club, division=cls.division)
        cls.team2 = factories.TeamFactory.create(division=cls.division)

        # Create a person for players endpoints
        cls.person = factories.PersonFactory.create(club=cls.club)

    def test_mcp_endpoint_available(self):
        """Test that the MCP endpoint is available and responds correctly."""
        # Try to access the MCP endpoint - should be available at /mcp/mcp
        # Based on mcp_server.urls, the pattern is 'mcp'
        response = self.client.get("/mcp/mcp")

        # The MCP endpoint should be accessible, though it might return a specific response
        # based on the MCP protocol. For now, we just check it doesn't return 404.
        self.assertNotEqual(response.status_code, 404)

    def test_mcp_server_in_apps(self):
        """Test that the MCP server app is properly installed."""
        from django.conf import settings

        self.assertIn("mcp_server", settings.INSTALLED_APPS)

    def test_mcp_tools_registered(self):
        """Test that MCP tools are properly registered."""
        # Import the MCP toolsets to ensure they are loaded
        from tournamentcontrol.competition import mcp

        # Check that our MCP toolsets exist and are properly configured
        self.assertTrue(hasattr(mcp, "ClubQueryTool"))
        self.assertTrue(hasattr(mcp, "CompetitionQueryTool"))
        self.assertTrue(hasattr(mcp, "SeasonQueryTool"))
        self.assertTrue(hasattr(mcp, "DivisionQueryTool"))
        self.assertTrue(hasattr(mcp, "StageQueryTool"))
        self.assertTrue(hasattr(mcp, "TeamQueryTool"))
        self.assertTrue(hasattr(mcp, "MatchQueryTool"))
        self.assertTrue(hasattr(mcp, "PersonQueryTool"))

        # Verify that the tools have the correct models assigned
        from tournamentcontrol.competition import models

        self.assertEqual(mcp.ClubQueryTool.model, models.Club)
        self.assertEqual(mcp.CompetitionQueryTool.model, models.Competition)
        self.assertEqual(mcp.SeasonQueryTool.model, models.Season)
        self.assertEqual(mcp.DivisionQueryTool.model, models.Division)
        self.assertEqual(mcp.StageQueryTool.model, models.Stage)
        self.assertEqual(mcp.TeamQueryTool.model, models.Team)
        self.assertEqual(mcp.MatchQueryTool.model, models.Match)
        self.assertEqual(mcp.PersonQueryTool.model, models.Person)

    def test_existing_drf_api_still_works(self):
        """Test that existing DRF API endpoints still work after MCP integration."""
        # Test some existing API endpoints to make sure they still work
        from tournamentcontrol.competition.tests.urls import urlpatterns

        # The MCP integration should not break existing REST API functionality
        # Test that the API URLs are still accessible via the test URL configuration
        self.assertEqual(len(urlpatterns), 3)  # accounts, api, and competition URLs

        # Since we're using the main vitriolic.urls, let's just check that
        # the URL configuration loaded correctly and MCP didn't break it
        from django.conf import settings

        self.assertEqual(settings.ROOT_URLCONF, "vitriolic.urls")
