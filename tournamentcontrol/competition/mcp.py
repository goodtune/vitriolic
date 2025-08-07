"""
Django MCP Server Integration for Tournament Control Competition API.

This module provides Model Context Protocol (MCP) integration for the vitriolic
tournament control system, allowing AI agents and MCP clients to interact with
the competition management system alongside existing REST API endpoints.

Overview
--------
The MCP integration exposes tournament management models as query tools through
the standardized Model Context Protocol, providing dual protocol support without
breaking existing DRF API functionality.

Available MCP Query Tools
-------------------------
The following models are exposed as MCP query tools:

- ClubQueryTool: Query and retrieve club information
- CompetitionQueryTool: Query competitions
- SeasonQueryTool: Query seasons within competitions
- DivisionQueryTool: Query divisions within seasons
- StageQueryTool: Query stages within divisions
- TeamQueryTool: Query teams
- MatchQueryTool: Query matches
- PersonQueryTool: Query players/persons

Technical Implementation
------------------------
Dependencies: django-mcp-server>=0.5.5 added to pyproject.toml

Configuration:
- INSTALLED_APPS: Added 'mcp_server' and 'rest_framework'
- URL Configuration: MCP URLs available at /mcp/ endpoint
- MCP Server Config: Named 'vitriolic-mcp-server' with tournament-specific instructions

Usage
-----
MCP clients can connect to the /mcp/mcp endpoint and use the available query tools
to retrieve data from the tournament management system. AI agents supporting MCP
can interact with tournament data through the standardized protocol.

Benefits:
- Dual Protocol Support: Both REST and MCP protocols available
- AI Agent Integration: Easy integration with AI agents and MCP clients
- Zero Breaking Changes: Existing DRF API endpoints remain fully functional
- Minimal Code Changes: Surgical integration without disrupting existing codebase

Testing
-------
Run MCP integration tests:
    uvx tox -e dj52-py312 -- tournamentcontrol.competition.tests.test_mcp_integration

Verify existing API compatibility:
    uvx tox -e dj52-py312 -- tournamentcontrol.competition.tests.test_rest_api_v1

Links
-----
- Django MCP Server: https://github.com/omarbenhamid/django-mcp-server
- MCP Specification: https://modelcontextprotocol.io/
"""

from mcp_server import ModelQueryToolset

from tournamentcontrol.competition.models import (
    Club,
    Competition,
    Division,
    Match,
    Person,
    Season,
    Stage,
    Team,
)


class ClubQueryTool(ModelQueryToolset):
    """Query tool for Club model - allows MCP clients to query clubs."""

    model = Club


class CompetitionQueryTool(ModelQueryToolset):
    """Query tool for Competition model - allows MCP clients to query competitions."""

    model = Competition


class SeasonQueryTool(ModelQueryToolset):
    """Query tool for Season model - allows MCP clients to query seasons."""

    model = Season


class DivisionQueryTool(ModelQueryToolset):
    """Query tool for Division model - allows MCP clients to query divisions."""

    model = Division


class StageQueryTool(ModelQueryToolset):
    """Query tool for Stage model - allows MCP clients to query stages."""

    model = Stage


class TeamQueryTool(ModelQueryToolset):
    """Query tool for Team model - allows MCP clients to query teams."""

    model = Team


class MatchQueryTool(ModelQueryToolset):
    """Query tool for Match model - allows MCP clients to query matches."""

    model = Match


class PersonQueryTool(ModelQueryToolset):
    """Query tool for Person model - allows MCP clients to query persons/players."""

    model = Person
