# MCP tools for competition management

`tournamentcontrol.competition` publishes a set of
[Model Context Protocol](https://modelcontextprotocol.io/) tools so an AI
agent can answer the questions people actually ask about a competition:

- "When is my next game?"
- "What time are Australia playing New Zealand?"
- "Who is top of Pool A?"
- "How many Men's games versus Women's games are being live streamed at the
  Euros?"

The tools live in `tournamentcontrol/competition/mcp.py` and are served by
[django-mcp-server](https://github.com/omarbenhamid/django-mcp-server) over
its Streamable HTTP transport. They are purpose-built for schedules and
results rather than a generic query layer over the models: every tool
answers a human-shaped question and returns compact JSON an agent can reason
over. Player statistics ("how many tries did Dylan score against NZ?") are a
natural future addition and are deliberately out of scope for now.

## How an agent is expected to work

The server instructions (returned by the `get_server_instructions` tool)
describe the data model and the recommended approach:

1. **Narrow the surface area.** `upcoming_events` and `recent_events` list
   the seasons (events) that are on now, soon, or just finished. `search`
   turns a name ("Australia", "Euros2026", "Women's Open", "Nottingham")
   into identifiers. `get_season` describes one event's divisions, stages,
   pools and venues.
2. **Answer with the detail tools** using those identifiers: `list_matches`,
   `count_matches`, `get_ladder`, `get_team` and `get_match`.
3. **For "my" questions** call `whoami` first. When the MCP client is
   authenticated it returns the user's teams with their next and last
   match; when it is anonymous the agent is told to ask which team or club
   the person follows.

Times are reported in the local time of the venue (falling back to the
season) as ISO 8601 with a UTC offset, alongside the time zone name.

## Tools

| Tool | Answers |
| --- | --- |
| `upcoming_events(days=30, limit=20)` | Which events are in progress or start within `days`, with first/last match dates, hashtag, time zone and whether they are live streamed. |
| `recent_events(days=30, limit=20)` | Which events had matches in the last `days`, most recently active first. |
| `search(query, limit=10)` | Competitions, seasons, divisions, teams, clubs and venues whose names contain every word of `query`, with the identifiers the other tools need. |
| `get_season(season_id)` | Divisions with their stages and pools, venues and grounds, span of dates and match counts (total, completed, upcoming, live streamed). |
| `list_teams(season_id, division_id, club_id, query, limit=100)` | Teams narrowed by season, division, club and/or name. |
| `get_team(team_id)` | A team's club, division, season, next and last match (byes excluded) and its position on each ladder. |
| `list_matches(...)` | Fixtures and results filtered by competition, season, division, stage, venue, team or club (either side), opponent team or club, date range, status (`upcoming`, `past`, `completed`, `any`) and live stream; paged and ordered by kick-off. |
| `count_matches(group_by, ...)` | The same filters as `list_matches`, returning counts (total, completed, live streamed) optionally grouped by competition, season, division, stage, pool, date, venue, live stream or status. |
| `get_match(match_id)` | Full detail of one match including venue coordinates and video links. |
| `get_ladder(division_id or stage_id)` | Standings for every stage of a division that keeps a ladder, split into pools. |
| `whoami()` | The connected user's person, club and teams, each with next and last match. |

Every tool follows the visibility rules of the public web site: only enabled
competitions and seasons are returned, and divisions marked as draft are
hidden unless the calling user is a superuser.

### Worked examples

*"What time are Australia playing New Zealand at the Euros?"*

1. `upcoming_events()` → the European Championships 2026 season is
   `in_progress`, `season_id` 12.
2. `search("Australia")` and `search("New Zealand")` → club identifiers 3
   and 7 (in international events the club is the nation).
3. `list_matches(season_id=12, club_id=3, opponent_club_id=7, status="upcoming")`
   → one match per division the two nations meet in, each with its local
   kick-off time, ground and live stream link.

*"How many Men's games vs Women's games are being live streamed at the Euros?"*

1. `upcoming_events()` → `season_id` 12.
2. `count_matches(season_id=12, group_by="division")` → one row per
   division with `count` and `live_streamed`.

*"When is my next game?"*

1. `whoami()` → the user's teams, each with `next_match`; or, if
   anonymous, ask which team they play for and use `search` + `get_team`.

## Deployment

A project needs the following to serve the tools.

1. Install `mcp_server` and `rest_framework` in `INSTALLED_APPS` (the
   `mcp.py` module of every installed app is autodiscovered, which is how
   `tournamentcontrol.competition.mcp` is registered).
2. Route the endpoint, for example `path("mcp/", include("mcp_server.urls"))`
   which serves the Streamable HTTP transport at `/mcp/mcp`.
3. Configure the server. Each MCP request is self-contained so the server
   should be stateless; the project's own instructions are prepended to the
   competition instructions that `tournamentcontrol.competition.mcp` appends:

    ```python
    DJANGO_MCP_GLOBAL_SERVER_CONFIG = {
        "name": "my-club-mcp-server",
        "instructions": "Schedules and results for the My Club touch competition.",
        "stateless": True,
    }
    ```

4. Optionally require authentication so `whoami` can identify the caller
   and superusers can see draft divisions:

    ```python
    DJANGO_MCP_AUTHENTICATION_CLASSES = [
        "rest_framework.authentication.SessionAuthentication",
    ]
    ```

    When this setting is present every MCP request must be authenticated.
    Leave it unset to serve public schedules and results anonymously.

## Testing

```bash
uvx tox -e dj52-py313 -- tournamentcontrol.competition.tests.test_mcp_integration
```

The tests call the toolset directly with a fake request (the way
`django-mcp-server` invokes it) and also drive the tools end-to-end over
JSON-RPC through the HTTP endpoint.
