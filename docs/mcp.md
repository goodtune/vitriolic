# MCP tools for competition management

`tournamentcontrol.competition` publishes a set of
[Model Context Protocol](https://modelcontextprotocol.io/) tools so an AI
agent can answer the questions people actually ask about a competition:

- "When is my next game?"
- "What time are Australia playing New Zealand?"
- "Who is top of Pool A?"
- "How many Men's games versus Women's games are being live streamed at the
  Euros?"

The tools live in `tournamentcontrol/competition/mcp/` and are served by
the official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
(`mcp` 2.x) over its Streamable HTTP transport, hosted from an ordinary
Django view so that Django's middleware, sessions and authentication apply.
They are purpose-built for schedules and results rather than a generic
query layer over the models: every tool answers a human-shaped question and
returns compact JSON an agent can reason over. Player statistics ("how many
tries did Dylan score against NZ?") are a natural future addition and are
deliberately out of scope for now.

## How an agent is expected to work

The server instructions (sent to the client when it connects) describe the
data model and the recommended approach:

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

Every tool is published with a human readable `title` (at the top level and
again as `annotations.title`, which is where the Claude connector directory
reads it) and the annotations `readOnlyHint: true` and
`destructiveHint: false`. Clients such as Claude
use these to run the tools without asking the user to approve each call,
and the Claude and ChatGPT connector directories require them on every tool
before a server can be listed.

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

1. Route the endpoint, for example
   `path("mcp/", include("tournamentcontrol.competition.mcp.urls"))`, which
   serves the Streamable HTTP transport at `/mcp/`. Point MCP clients at
   that URL.
2. Optionally name and describe the server. The project's own instructions
   are placed ahead of the competition instructions so an agent reads the
   project context first:

    ```python
    TOURNAMENTCONTROL_MCP_NAME = "my-club"
    TOURNAMENTCONTROL_MCP_INSTRUCTIONS = (
        "Schedules and results for the My Club touch competition."
    )
    ```

Every request is served statelessly, so no MCP session state is kept
between calls and the endpoint can sit behind any number of workers or
instances with no session affinity. Only `POST` is served: in the
Streamable HTTP transport `GET` opens a server-to-client event stream and
`DELETE` ends a session, neither of which a stateless server uses, and a
synchronous WSGI worker (gunicorn's default) could not hold a stream open
anyway. Both answer `405 Method Not Allowed`, as the specification allows,
so a stray browser or link checker cannot tie up a worker.

MCP clients should be given the site's canonical `https` URL directly. A
`POST` that is redirected (for example from `http` to `https`, or to add
`www`) is not replayed by clients, and the MCP Python client only follows
redirects within the endpoint's own origin.

The tools see the Django request that carried the MCP call. `whoami`
identifies the caller from `request.user`, so a client that presents a
Django session cookie is recognised, as is one presenting an OAuth 2.0
bearer token when the project runs an authorization server (see
[MCP tools for competition administration](mcp-admin.md), which describes
the django-oauth-toolkit setup; a token is only accepted by the endpoint it
was issued for); anonymous clients still get the public schedules and
results. To serve a different `MCPServer` (for example one that adds
project-specific tools with
`tournamentcontrol.competition.mcp.build_server`) pass it to the view:
`MCPView.as_view(server=my_server)`.

A second server for competition *administrators*, with tools that create
and change competitions, schedule matches, enter results and manage live
streams, is described in [mcp-admin.md](mcp-admin.md).

## Observing tool calls

Each request the public and administration endpoints answer sends the
`tournamentcontrol.competition.mcp.signals.mcp_request_handled` signal,
so a project can log or count how its MCP servers are used without
patching the views. The receiver is given the Django `request`, the
JSON-RPC `method`, the `tool` a `tools/call` asked for, its `arguments`
exactly as the client sent them (before validation, so rejected arguments
are there too; they can include personal details, so take care where they
are written), the `duration` in
seconds the tool ran for (`None` if it did not run), and `error`: `None`
on success, otherwise the class name of the exception the tool raised,
`"isError"` for a result the SDK marked as an error without the tool
raising (arguments that failed validation, an unknown tool), or
`"jsonrpc"` for a JSON-RPC error. A failed tool still answers with HTTP
200, so `error` is the only place the failure shows.

```python
from django.dispatch import receiver

from tournamentcontrol.competition.mcp.signals import mcp_request_handled


@receiver(mcp_request_handled)
def log_mcp_request(
    sender, request, method, tool, arguments, duration, error, **kwargs
):
    ...
```

Receivers run in the request thread once the response is built. An
exception in a receiver is logged and does not change the response. A
request refused before it reaches the MCP server (a `401` or `403` from
the administration endpoint, a `405`) does not send the signal.

## Testing

```bash
uvx tox -e dj52-py313 -- tournamentcontrol.competition.tests.test_mcp_integration
```

The tests call the toolset directly with a fake request and also drive the
tools over JSON-RPC through the HTTP endpoint. The end-to-end suite
(`tox -e e2e -- e2e/test_mcp_client.py`) connects the official MCP client
to a live server.
