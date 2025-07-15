"""
MCP (Model Context Protocol) tools for Tournament Control Competition API.

This module exposes Django models as MCP tools,
allowing AI agents and MCP clients to interact with the competition system.
"""

from mcp_server import ModelQueryToolset

from .models import (
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

    def get_queryset(self):
        """Return active clubs."""
        return super().get_queryset()


class CompetitionQueryTool(ModelQueryToolset):
    """Query tool for Competition model - allows MCP clients to query competitions."""

    model = Competition

    def get_queryset(self):
        """Return active competitions."""
        return super().get_queryset()


class SeasonQueryTool(ModelQueryToolset):
    """Query tool for Season model - allows MCP clients to query seasons."""

    model = Season

    def get_queryset(self):
        """Return seasons."""
        return super().get_queryset()


class DivisionQueryTool(ModelQueryToolset):
    """Query tool for Division model - allows MCP clients to query divisions."""

    model = Division

    def get_queryset(self):
        """Return divisions."""
        return super().get_queryset()


class StageQueryTool(ModelQueryToolset):
    """Query tool for Stage model - allows MCP clients to query stages."""

    model = Stage

    def get_queryset(self):
        """Return stages."""
        return super().get_queryset()


class TeamQueryTool(ModelQueryToolset):
    """Query tool for Team model - allows MCP clients to query teams."""

    model = Team

    def get_queryset(self):
        """Return teams."""
        return super().get_queryset()


class MatchQueryTool(ModelQueryToolset):
    """Query tool for Match model - allows MCP clients to query matches."""

    model = Match

    def get_queryset(self):
        """Return matches."""
        return super().get_queryset()


class PersonQueryTool(ModelQueryToolset):
    """Query tool for Person model - allows MCP clients to query persons/players."""

    model = Person

    def get_queryset(self):
        """Return persons."""
        return super().get_queryset()
