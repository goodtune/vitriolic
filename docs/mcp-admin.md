# MCP tools for competition administration

Alongside the public, read-only [MCP tools](mcp.md) at `/mcp/`,
`tournamentcontrol.competition` publishes a second
[Model Context Protocol](https://modelcontextprotocol.io/) server for
*competition administrators*, intended to be mounted at `/admin/mcp/`. It
does the work an administrator does in the admin site: building a
competition up from scratch, scheduling, result entry, referee appointments
and live streaming. The read-only tools are available on it too, with
administrator visibility (disabled competitions and draft divisions
included).

The tools live in `tournamentcontrol/competition/mcp/admin/` and are served
by `AdminMCPView` in `tournamentcontrol/competition/mcp/views.py`.

## Authentication

The administration endpoint requires a signed-in **staff** user, the same
gate as the admin site. A client identifies itself the way any other HTTP
client of the site does:

- a Django **session cookie**, recognised by the authentication middleware;
- an OAuth 2.0 **bearer token** in the `Authorization` header, handed to the
  configured authentication backends with `django.contrib.auth.authenticate`
  so a backend that understands access tokens can turn it into
  `request.user`.

An anonymous caller is answered with `401 Unauthorized` and a
`WWW-Authenticate: Bearer resource_metadata="…"` challenge (RFC 9728). That
header is what lets an MCP client find out, with no configuration beyond
the URL, how to obtain a token:

1. it fetches the **protected resource metadata** named in the challenge
   (`/.well-known/oauth-protected-resource/admin/mcp/`), which names the
   authorization server;
2. it fetches the **authorization server metadata** (RFC 8414) to find the
   authorization, token and registration endpoints;
3. it **registers itself** dynamically (RFC 7591) as a public client with
   its redirect URL;
4. it opens the browser on the **authorization endpoint**; the person signs
   in to the site (the usual login page) and approves the client;
5. it exchanges the code for an access token and a refresh token with
   **PKCE** (RFC 7636), and retries the call with the token.

This is the flow in the MCP authorization specification and it is what
Claude Code, Claude.ai and ChatGPT connectors, Cursor and the MCP inspector
all implement. Tokens are bound to the resource they were requested for
(RFC 8707), so a token obtained for `/admin/mcp/` is not accepted anywhere
else on the site.

### The authorization server: django-oauth-toolkit

Rather than ship a bespoke authorization server, the project relies on
[django-oauth-toolkit](https://django-oauth-toolkit.readthedocs.io/) (3.4 or
later), which implements everything the flow needs: PKCE, dynamic client
registration, the RFC 8414 and RFC 9728 discovery documents, resource
indicators, refresh token rotation and hashed-at-rest tokens, and gives
users a page to review and revoke the clients they have authorised. It is
installed with the `competition` extra.

1. Add the application and its authentication backend:

    ```python
    INSTALLED_APPS = [
        ...
        "oauth2_provider",
        ...
    ]

    AUTHENTICATION_BACKENDS = (
        "django.contrib.auth.backends.ModelBackend",
        "guardian.backends.ObjectPermissionBackend",
        "oauth2_provider.backends.OAuth2Backend",
    )
    ```

2. Configure the provider for public MCP clients:

    ```python
    OAUTH2_PROVIDER = {
        "PKCE_REQUIRED": True,
        "COMPLIANT_BCP_RFC9700_PKCE_METHOD": True,
        # Claude Code redirects to http://localhost:<port>/callback.
        "ALLOWED_REDIRECT_URI_SCHEMES": ["https", "http"],
        "SCOPES": {
            "competition": "Read and administer competitions on your behalf",
        },
        "DEFAULT_SCOPES": ["competition"],
        "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,
        "REFRESH_TOKEN_EXPIRE_SECONDS": 60 * 60 * 24 * 30,
        "ROTATE_REFRESH_TOKEN": True,
        # Public clients authenticate with PKCE alone.
        "OAUTH2_TOKEN_ENDPOINT_AUTH_METHODS_SUPPORTED": [
            "none",
            "client_secret_post",
            "client_secret_basic",
        ],
        # MCP clients register themselves before the person has signed in.
        "DCR_ENABLED": True,
        "DCR_REGISTRATION_PERMISSION_CLASSES": (
            "oauth2_provider.dcr.AllowAllDCRPermission",
        ),
        "OAUTH2_PROTECTED_RESOURCE_NAME": "Tournament Control",
    }
    ```

3. Route the endpoints. The discovery documents must be served from the
   site root (`/.well-known/...`); the authorization server itself can live
   under a prefix:

    ```python
    from oauth2_provider.urls import metadata_urlpatterns

    urlpatterns = [
        path("admin/mcp/", include("tournamentcontrol.competition.mcp.admin.urls")),
        path("admin/", site.urls),
        path("mcp/", include("tournamentcontrol.competition.mcp.urls")),
        path("o/", include("oauth2_provider.urls", namespace="oauth2_provider")),
        path(
            "",
            include((metadata_urlpatterns, "oauth2_provider"), namespace="oauth2_discovery"),
        ),
        ...
    ]
    ```

4. Run `migrate` to create the provider's tables, and serve the site over
   HTTPS (the discovery documents and the token endpoint are only trusted
   over `https`; `http` is accepted for `localhost` during development).

A person can see and revoke the clients they have authorised at
`/o/authorized_tokens/`. The `OAUTH2_PROVIDER` setting is documented in
full by django-oauth-toolkit; the `MCP_NAME`/`MCP_INSTRUCTIONS` settings of
the public server have `TOURNAMENTCONTROL_MCP_ADMIN_NAME` and
`TOURNAMENTCONTROL_MCP_ADMIN_INSTRUCTIONS` counterparts for this one (the
instructions fall back to the public ones).

### Connecting Claude Code

```bash
claude mcp add --transport http tournamentcontrol-admin https://example.com/admin/mcp/
```

The first call is refused with the challenge above, and Claude Code offers
to authenticate (`/mcp` → the server → *Authenticate*): it opens the
browser on the site's login page, the person signs in and approves the
client, and the token is stored for future sessions and refreshed as it
expires. The same URL works as a custom connector in Claude.ai, where the
flow is identical.

## Authorization

Being signed in is not enough: each tool checks the model permission the
equivalent admin view checks, accepted either globally or on the specific
record through django-guardian, exactly as `generic_edit` and
`generic_delete` in `touchtechnology.common.sites` do.

| Tools | Permission |
| --- | --- |
| `create_*` | `competition.add_<model>` |
| `update_*`, `reschedule_match`, `swap_match_allocations`, `set_match_referees`, `record_match_result`, `enable_*_live_stream`, `disable_*_live_stream` | `competition.change_<model>` (globally or on the record) |
| `delete_*` | `competition.delete_<model>` (globally or on the record) |
| `list_season_stream_keys`, `list_streamed_grounds` (they reveal stream keys) | `competition.change_season` for the season |
| other `list_*` tools and the inherited read tools | a staff user |

A superuser has every permission. Anyone else needs the permissions granted
from the admin site's users and groups pages, or on individual
competitions, seasons and teams from their permissions tab.

## Tools

Every tool that changes data returns `saved: true` with the record as
saved; a tool that cannot proceed returns an error result whose message
explains why (missing permission, record not found, a validation failure
from the form, or a rule such as "the stream key is in use").

### Building a competition

| Tool | Does |
| --- | --- |
| `list_competitions()` | Every competition, enabled or not, with its seasons. |
| `create_competition`, `update_competition(competition_id, …)`, `delete_competition(competition_id)` | Title, short title, enabled, notes, clubs, MySideline URL (`CompetitionForm`). |
| `create_season(competition_id, title, …)`, `update_season(season_id, …)`, `delete_season(season_id)` | Time zone, start date, mode (season or tournament), hashtag, statistics, complete, live stream flag and privacy, YouTube credentials (`SeasonForm`). |
| `list_venues(season_id)` | Venues and grounds with time zones and coordinates. |
| `create_venue(season_id, title, latitude, longitude, zoom, …)`, `update_venue`, `delete_venue` | `VenueForm`. |
| `create_ground(venue_id, title, …, live_stream)`, `update_ground`, `delete_ground` | `GroundForm`, with the YouTube stream kept in step as the admin's ground view does. |
| `create_division(season_id, title, points_formula, …)`, `update_division`, `delete_division` | `DivisionForm`, including the points formula validation. |
| `create_team(division_id, title or club_id, …)`, `update_team`, `delete_team` | `TeamForm`; a team with matches cannot be deleted. |
| `create_stage(division_id, title, …)`, `update_stage`, `delete_stage` | `StageForm`. |
| `create_pool(stage_id, title)`, `update_pool(pool_id, team_ids, …)`, `delete_pool` | `StageGroupForm`; membership can only change while the pool has no matches. |
| `create_match(stage_id, home_team_id, away_team_id, date, time, place_id, …)`, `update_match`, `delete_match` | `MatchEditForm` (or `MatchStreamForm` in a live streamed season), then the scheduling rules below for the time and place. |

Only the arguments given to an `update_*` tool are changed: the form is
bound to the record's current values with the changes laid over them, so
the validation and side effects of a form submission from the admin site
apply (for example changing a division's points formula recalculates its
ladders, and changing a venue's time zone recomputes kick-off instants).

### Scheduling

| Tool | Does |
| --- | --- |
| `reschedule_match(match_id, date, time, place_id, ignore_clashes)` | Sets the date, time and/or place with the rules of the admin scheduler: not before the season starts nor on an excluded date (`Match.clean`), the teams' time preferences (`MatchScheduleForm`), and, unless `ignore_clashes`, no other match at the same place and time that day and no declared team clash (`MatchScheduleFormSet`). The kick-off instant is recomputed in the place's time zone. |
| `swap_match_allocations(match_id, other_match_id)` | Exchanges the date, time and place of two matches of the same season. |

A match that is live streamed is not moved off a streamed ground and is
never swapped: remove its live stream first. Moving it between streamed
grounds resynchronises its broadcast.

### Results and referees

| Tool | Does |
| --- | --- |
| `list_matches_awaiting_results(season_id, division_id, date)` | Matches that have kicked off without a result, as the admin dashboard lists them. |
| `record_match_result(match_id, home_team_score, away_team_score, is_forfeit, forfeit_winner_id, bye_processed)` | Enters or revises a result through `MatchResultForm`; the ladders are updated by the same signals as the admin. |
| `list_season_referees(season_id)` | The referees registered for the season. |
| `set_match_referees(match_id, referee_ids)` | Replaces the appointments through `MatchRefereeForm`. |

### Live streaming

| Tool | Does |
| --- | --- |
| `list_season_stream_keys(season_id)` | The stream keys not tied to a ground (used by ad-hoc events), with their YouTube stream ids and usage. |
| `list_season_stream_events(season_id)` | The ad-hoc live stream events (broadcasts that are not a match). |
| `list_streamed_grounds(season_id)` | The grounds that are camera positions, with their stream keys and upcoming streamed matches. |
| `create_season_stream_key(season_id, title)` | Creates the YouTube stream and stores its key. |
| `delete_season_stream_key(season_id, stream_key_id)` | Refused while an event uses it; the stream is removed from YouTube first. |
| `enable_ground_live_stream(ground_id)` | Creates the ground's YouTube stream and returns its key. |
| `disable_ground_live_stream(ground_id)` | Refused while an upcoming match on the ground is set to be streamed; removes the stream from YouTube. |
| `enable_match_live_stream(match_id)` | Requires a streamed ground; queues the broadcast creation and binding (`sync_live_stream`). |
| `disable_match_live_stream(match_id)` | Requires the match to be streamed; queues the broadcast removal. |

The YouTube side effects are the ones the admin views perform around the
forms (`edit_ground`, `edit_livestreamkey`, `delete_livestreamkey`,
`edit_match`); they need the season's YouTube credentials and authorisation,
which are configured from the admin site.

## Tool annotations

The read tools carry `readOnlyHint: true`; every tool that changes data is
published with `readOnlyHint: false`, `destructiveHint: true` where it
deletes or withdraws something, `idempotentHint: true` where repeating it
has no further effect, and `openWorldHint: true` where it also acts on
YouTube. Clients use these to decide when to ask the person before running
a tool.

## Testing

```bash
uvx tox -e dj52-py313 -- tournamentcontrol.competition.tests.test_mcp_admin
```

The tests call the toolset directly with a fake request, drive the tools
over JSON-RPC through the HTTP endpoint with a session, and run the
complete OAuth flow (registration, authorization with PKCE, token exchange,
refresh) against django-oauth-toolkit before calling the tools with the
bearer token.
