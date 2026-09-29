"""
End-to-end tests driving the competition MCP server with the official MCP
client over Streamable HTTP, exactly as an agent would.
"""

import datetime
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from mcp.client import Client

from tournamentcontrol.competition.tests import factories

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]


@pytest.fixture
def fixture(db):
    """A season with one completed and one upcoming match."""
    club = factories.ClubFactory.create(title="Australia")
    opponent = factories.ClubFactory.create(title="New Zealand")
    competition = factories.CompetitionFactory.create(title="World Cup")
    season = factories.SeasonFactory.create(
        competition=competition, title="2027", timezone=ZoneInfo("UTC")
    )
    division = factories.DivisionFactory.create(season=season, title="Men's Open")
    stage = factories.StageFactory.create(division=division)
    home = factories.TeamFactory.create(club=club, division=division, title="Australia")
    away = factories.TeamFactory.create(
        club=opponent, division=division, title="New Zealand"
    )
    today = timezone.now().date()
    last_week = datetime.datetime.combine(
        today - datetime.timedelta(days=7), datetime.time(10, 0), ZoneInfo("UTC")
    )
    next_week = datetime.datetime.combine(
        today + datetime.timedelta(days=7), datetime.time(10, 0), ZoneInfo("UTC")
    )
    played = factories.MatchFactory.create(
        stage=stage,
        home_team=home,
        away_team=away,
        datetime=last_week,
        home_team_score=8,
        away_team_score=6,
    )
    upcoming = factories.MatchFactory.create(
        stage=stage,
        home_team=away,
        away_team=home,
        datetime=next_week,
    )
    return {
        "season": season,
        "club": club,
        "opponent": opponent,
        "home": home,
        "played": played,
        "upcoming": upcoming,
    }


async def test_list_tools(live_server, fixture):
    """The server advertises the competition tools with their schemas."""
    async with Client(f"{live_server.url}/mcp/") as client:
        result = await client.list_tools()
    tools = {tool.name: tool for tool in result.tools}
    assert {
        "upcoming_events",
        "recent_events",
        "search",
        "get_season",
        "list_teams",
        "get_team",
        "list_matches",
        "count_matches",
        "get_match",
        "get_ladder",
        "whoami",
    } <= set(tools)
    assert tools["list_matches"].input_schema["properties"]["status"]["enum"] == [
        "any",
        "upcoming",
        "past",
        "completed",
    ]


async def test_instructions(live_server, fixture):
    """The server instructions teach the agent how to use the tools."""
    async with Client(f"{live_server.url}/mcp/") as client:
        assert "Narrow the surface area first" in client.instructions


async def test_schedule_and_results(live_server, fixture):
    """Answer "when are Australia playing New Zealand?" the way an agent would."""
    async with Client(f"{live_server.url}/mcp/") as client:
        events = await client.call_tool("upcoming_events", {"days": 30})
        assert events.is_error is False
        assert [e["title"] for e in events.structured_content["events"]] == [
            "World Cup 2027"
        ]

        found = await client.call_tool("search", {"query": "Australia"})
        assert [c["club"]["id"] for c in found.structured_content["clubs"]] == [
            fixture["club"].pk
        ]

        matches = await client.call_tool(
            "list_matches",
            {
                "season_id": fixture["season"].pk,
                "club_id": fixture["club"].pk,
                "opponent_club_id": fixture["opponent"].pk,
            },
        )
        assert [m["id"] for m in matches.structured_content["matches"]] == [
            fixture["played"].pk,
            fixture["upcoming"].pk,
        ]
        assert matches.structured_content["matches"][0]["status"] == "completed"
        assert matches.structured_content["matches"][0]["winner"]["id"] == (
            fixture["home"].pk
        )
        assert matches.structured_content["matches"][1]["status"] == "upcoming"

        team = await client.call_tool("get_team", {"team_id": fixture["home"].pk})
        assert team.structured_content["next_match"]["id"] == fixture["upcoming"].pk
        assert team.structured_content["last_match"]["id"] == fixture["played"].pk


async def test_anonymous_whoami(live_server, fixture):
    """Without authentication the agent is told to ask which team to follow."""
    async with Client(f"{live_server.url}/mcp/") as client:
        result = await client.call_tool("whoami", {})
    assert result.structured_content["authenticated"] is False


async def test_unknown_tool(live_server, fixture):
    """Calling a tool that does not exist is reported as an error."""
    async with Client(f"{live_server.url}/mcp/") as client:
        result = await client.call_tool("nonexistent_tool", {})
    assert result.is_error is True
