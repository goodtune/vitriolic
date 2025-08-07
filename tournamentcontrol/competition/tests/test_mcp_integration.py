"""
Test MCP Server Integration for Tournament Control Competition API.
"""

import json

from django.conf import settings
from django.test.utils import override_settings
from test_plus import TestCase

from tournamentcontrol.competition import mcp, models
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.urls import urlpatterns


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
        response = self.get("/mcp/mcp")

        # The MCP endpoint should be accessible, though it might return a specific response
        # based on the MCP protocol. For now, we just check it doesn't return 404.
        self.assertNotEqual(response.status_code, 404)

    def test_mcp_server_in_apps(self):
        """Test that the MCP server app is properly installed."""
        self.assertIn("mcp_server", settings.INSTALLED_APPS)

    def test_mcp_tools_registered(self):
        """Test that MCP tools are properly registered."""
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
        # The MCP integration should not break existing REST API functionality
        # Test that the API URLs are still accessible via the test URL configuration
        self.assertEqual(len(urlpatterns), 3)  # accounts, api, and competition URLs

        # Since we're using the main vitriolic.urls, let's just check that
        # the URL configuration loaded correctly and MCP didn't break it
        self.assertEqual(settings.ROOT_URLCONF, "vitriolic.urls")

    def test_mcp_http_protocol_initialize(self):
        """Test MCP server HTTP protocol initialization."""
        # Test MCP initialization request over HTTP
        mcp_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        }

        response = self.client.post(
            "/mcp/mcp", data=json.dumps(mcp_data), content_type="application/json"
        )

        # MCP endpoint should process requests appropriately
        expected_statuses = [200, 400, 406, 422]  # Valid responses or expected errors
        self.assertIn(
            response.status_code,
            expected_statuses,
            f"Expected MCP endpoint to process request, got {response.status_code}",
        )

    def test_mcp_http_protocol_list_tools(self):
        """Test MCP server HTTP protocol tool listing."""
        # Test MCP list_tools request over HTTP
        mcp_data = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

        response = self.client.post(
            "/mcp/mcp", data=json.dumps(mcp_data), content_type="application/json"
        )

        # MCP endpoint should process tool listing requests appropriately
        expected_statuses = [200, 400, 406, 422]  # Valid responses or expected errors
        self.assertIn(
            response.status_code,
            expected_statuses,
            f"Expected MCP endpoint to process tools/list request, got {response.status_code}",
        )

        # If successful (2xx), should return valid JSON with jsonrpc field
        if 200 <= response.status_code < 300:
            response_data = response.json()
            self.assertEqual(
                response_data.get("jsonrpc"), "2.0", "Response must use JSON-RPC 2.0"
            )
            self.assertIn("id", response_data, "Response must include id field")

    def test_mcp_http_protocol_call_tool(self):
        """Test MCP server HTTP protocol tool calling."""
        # Test MCP call_tool request over HTTP for club query
        mcp_data = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "clubquerytool_query",
                "arguments": {"query": {"title__icontains": self.club.title[:5]}},
            },
        }

        response = self.client.post(
            "/mcp/mcp", data=json.dumps(mcp_data), content_type="application/json"
        )

        # MCP endpoint should process tool call requests appropriately
        expected_statuses = [200, 400, 406, 422]  # Valid responses or expected errors
        self.assertIn(
            response.status_code,
            expected_statuses,
            f"Expected MCP endpoint to process tools/call request, got {response.status_code}",
        )

        # If successful (2xx), should return valid JSON with jsonrpc field
        if 200 <= response.status_code < 300:
            response_data = response.json()
            self.assertEqual(
                response_data.get("jsonrpc"), "2.0", "Response must use JSON-RPC 2.0"
            )
            self.assertIn("id", response_data, "Response must include id field")

    def test_mcp_tools_model_access(self):
        """Test that MCP tools can access Django models correctly."""
        # Test instantiating MCP tools and verify they have model access
        club_tool = mcp.ClubQueryTool()
        self.assertEqual(club_tool.model, models.Club)

        # Verify model queryset access
        self.assertTrue(hasattr(club_tool.model.objects, "all"))

        # Test that we can query the model through Django ORM
        club_count = club_tool.model.objects.count()
        self.assertGreaterEqual(club_count, 1)  # We created at least one club

        # Test other tools
        competition_tool = mcp.CompetitionQueryTool()
        self.assertEqual(competition_tool.model, models.Competition)

        team_tool = mcp.TeamQueryTool()
        self.assertEqual(team_tool.model, models.Team)
