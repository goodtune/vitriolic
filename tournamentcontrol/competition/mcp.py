"""
MCP (Model Context Protocol) tools for Tournament Control Competition API.

This module exposes Django models as MCP tools,
allowing AI agents and MCP clients to interact with the competition system.
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
