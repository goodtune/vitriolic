"""
End-to-end tests driving the competition *administration* MCP server with
the official MCP client, including the OAuth 2.1 flow the client runs to
obtain a bearer token: discovery from the 401 challenge, dynamic client
registration, authorization in the "browser" with PKCE, and the token
exchange.
"""

import asyncio
import datetime
import threading
from types import SimpleNamespace
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx2
import pytest
import requests
from mcp.client import Client
from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientMetadata

from tournamentcontrol.competition.mcp.admin import AdminToolset
from tournamentcontrol.competition.models import Match, Season, Stage
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.utils import round_robin_format

pytestmark = pytest.mark.django_db(transaction=True)


def run(coroutine_function, *args):
    """Run an MCP client conversation on its own event loop in a worker thread."""
    outcome = {}

    def target():
        try:
            outcome["value"] = asyncio.run(coroutine_function(*args))
        except BaseException as exc:  # re-raised on the test thread below
            outcome["error"] = exc

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


class MemoryStorage:
    """Token storage for one conversation."""

    def __init__(self):
        self.tokens = None
        self.client_info = None

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, tokens):
        self.tokens = tokens

    async def get_client_info(self):
        return self.client_info

    async def set_client_info(self, client_info):
        self.client_info = client_info


class Person:
    """
    Stands in for the browser: follows the authorization URL the MCP client
    wants opened, signs in to the site and approves the client, then hands
    the authorization code back to the client.
    """

    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.result = None

    def _csrf(self):
        return self.session.cookies["csrftoken"]

    def _post(self, url, data):
        return self.session.post(
            url,
            data=dict(data, csrfmiddlewaretoken=self._csrf()),
            headers={"Referer": url},
            allow_redirects=False,
        )

    async def redirect_handler(self, authorization_url):
        # Anonymous: the authorization endpoint sends the person to log in.
        response = self.session.get(authorization_url, allow_redirects=False)
        assert response.status_code == 302, response.status_code
        login_url = urljoin(self.base_url, response.headers["Location"])
        assert urlparse(login_url).path == "/accounts/login/"
        self.session.get(login_url)
        response = self._post(
            login_url, {"username": self.username, "password": self.password}
        )
        assert response.status_code == 302, response.text
        # Signed in: the consent page names the client, and approving it
        # redirects to the client's callback with the code.
        response = self.session.get(authorization_url)
        assert response.status_code == 200
        assert "Claude Code (test)" in response.text
        params = {
            k: v[0] for k, v in parse_qs(urlparse(authorization_url).query).items()
        }
        response = self._post(authorization_url, dict(params, allow="Authorize"))
        assert response.status_code == 302, response.text
        callback = urlparse(response.headers["Location"])
        assert callback.netloc == "localhost:43110"
        query = parse_qs(callback.query)
        self.result = AuthorizationCodeResult(
            code=query["code"][0], state=query["state"][0]
        )

    async def callback_handler(self):
        return self.result


def client_for(live_server, person, storage=None):
    url = f"{live_server.url}/admin/mcp/"
    auth = OAuthClientProvider(
        server_url=url,
        client_metadata=OAuthClientMetadata(
            client_name="Claude Code (test)",
            redirect_uris=["http://localhost:43110/callback"],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
        ),
        storage=storage or MemoryStorage(),
        redirect_handler=person.redirect_handler,
        callback_handler=person.callback_handler,
    )
    http_client = httpx2.AsyncClient(
        auth=auth, timeout=httpx2.Timeout(30.0, read=300.0)
    )
    return Client(streamable_http_client(url, http_client=http_client))


@pytest.fixture
def fixture(db, django_user_model):
    """A season with a venue, a division, two teams and a stage, plus users."""
    competition = factories.CompetitionFactory.create(title="World Cup")
    season = factories.SeasonFactory.create(
        competition=competition, title="2027", timezone=ZoneInfo("UTC")
    )
    venue = factories.VenueFactory.create(
        season=season, title="Nottingham", latlng="52.95,-1.15,12"
    )
    ground = factories.GroundFactory.create(venue=venue, title="Field 1")
    division = factories.DivisionFactory.create(season=season, title="Men's Open")
    stage = factories.StageFactory.create(division=division)
    home = factories.TeamFactory.create(division=division, title="Australia")
    away = factories.TeamFactory.create(division=division, title="New Zealand")
    admin = django_user_model.objects.create_superuser(
        username="admin", password="password", email="admin@example.com"
    )
    member = django_user_model.objects.create_user(
        username="member", password="password", email="member@example.com"
    )
    return {
        "season": season,
        "ground": ground,
        "stage": stage,
        "home": home,
        "away": away,
        "admin": admin,
        "member": member,
    }


def test_anonymous_is_challenged(live_server, fixture):
    """Without a token the endpoint answers 401 with the discovery challenge."""
    response = requests.post(
        f"{live_server.url}/admin/mcp/",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == (
        'Bearer resource_metadata="%s/.well-known/oauth-protected-resource/admin/mcp/"'
        % live_server.url
    )


async def administer(live_server, person, fixture):
    async with client_for(live_server, person) as client:
        tools = await client.list_tools()
        whoami = await client.call_tool("whoami", {})
        match = await client.call_tool(
            "create_match",
            {
                "stage_id": fixture["stage"].pk,
                "home_team_id": fixture["home"].pk,
                "away_team_id": fixture["away"].pk,
                "date": "2027-03-06",
                "time": "10:30",
                "place_id": fixture["ground"].pk,
                "round": 1,
            },
        )
        result = await client.call_tool(
            "record_match_result",
            {
                "match_id": match.structured_content["match"]["id"],
                "home_team_score": 7,
                "away_team_score": 5,
            },
        )
        ladder = await client.call_tool("get_ladder", {"stage_id": fixture["stage"].pk})
    return tools, whoami, match, result, ladder


def test_oauth_flow_and_administration(live_server, fixture):
    """
    The client discovers the authorization server from the challenge,
    registers, is authorized by the administrator in the browser and then
    builds up and scores a match.
    """
    person = Person(live_server.url, "admin", "password")
    tools, whoami, match, result, ladder = run(administer, live_server, person, fixture)
    names = {tool.name for tool in tools.tools}
    assert {"create_match", "record_match_result", "get_ladder", "whoami"} <= names
    assert whoami.structured_content["username"] == "admin"
    assert match.is_error is False
    assert match.structured_content["match"]["datetime"] == "2027-03-06T10:30:00+00:00"
    assert match.structured_content["match"]["ground"]["title"] == "Field 1"
    assert result.structured_content["match"]["winner"]["title"] == "Australia"
    table = ladder.structured_content["stages"][0]["pools"][0]["ladder"]
    assert [(e["team"]["title"], e["points"]) for e in table] == [
        ("Australia", 3.0),
        ("New Zealand", 1.0),
    ]


async def list_tools(live_server, person, storage):
    async with client_for(live_server, person, storage) as client:
        return await client.list_tools()


def test_non_staff_is_forbidden(live_server, fixture):
    """A person who is not staff can authorize a client but is refused."""
    person = Person(live_server.url, "member", "password")
    storage = MemoryStorage()
    with pytest.raises(Exception):
        run(list_tools, live_server, person, storage)
    # The flow completed and issued a token; the endpoint refuses it.
    assert storage.tokens is not None
    response = requests.post(
        f"{live_server.url}/admin/mcp/",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer %s" % storage.tokens.access_token,
        },
    )
    assert response.status_code == 403
    assert response.json()["error"] == "forbidden"


# -- the demo competition ---------------------------------------------------

DEMO_DIVISIONS = (("Men's", 8), ("Women's", 6), ("Mixed", 10))
DEMO_GROUNDS = 4
DEMO_START = "2026-10-07"  # the first Wednesday of the season
DEMO_BREAK = ["2026-12-23", "2026-12-30", "2027-01-06"]
DEMO_SEMIS = "2027-01-20"
DEMO_SLOTS = ["18:40", "19:30", "20:20"]
DEMO_FINALS = (
    "ROUND Semi Finals\n"
    "1: P1 vs P4 Semi 1\n"
    "2: P2 vs P3 Semi 2\n"
    "ROUND Grand Final\n"
    "3: W1 vs W2 Final"
)

#: One call per record the agent has to name (competition, season, venue,
#: grounds, divisions, stages and teams): there are no batch tools for these.
DEMO_RECORD_CALLS = (
    3
    + DEMO_GROUNDS
    + 3 * len(DEMO_DIVISIONS)
    + sum(teams for __, teams in DEMO_DIVISIONS)
)
#: Everything else: time slots, exclusions, draw formats, building the draw
#: and scheduling it. Before ``build_draw`` and ``schedule_matches`` this was
#: one call per match (153).
DEMO_WORKFLOW_BUDGET = 15


async def build_demo(live_server, person):
    """
    Rebuild the demo competition the way an agent would with the MCP
    client, returning the identifiers and the tool calls made.
    """
    calls = []

    async with client_for(live_server, person) as client:

        async def call(name, arguments):
            calls.append(name)
            result = await client.call_tool(name, arguments)
            assert result.is_error is False, (name, result.content[0].text)
            return result.structured_content

        # 1. Competition, weekly season and a venue with four grounds.
        competition = await call("create_competition", {"title": "Demo League"})
        season = await call(
            "create_season",
            {
                "competition_id": competition["competition"]["id"],
                "title": "2026/27",
                "timezone": "Australia/Sydney",
                "start_date": DEMO_START,
                "mode": "season",
            },
        )
        season_id = season["season"]["id"]
        venue = await call(
            "create_venue",
            {
                "season_id": season_id,
                "title": "Park",
                "latitude": -33.8,
                "longitude": 151.2,
                "zoom": 14,
            },
        )
        grounds = []
        for n in range(1, DEMO_GROUNDS + 1):
            ground = await call(
                "create_ground",
                {"venue_id": venue["venue"]["id"], "title": f"Field {n}"},
            )
            grounds.append(ground["ground"]["id"])

        # 2. Three weeknight time slots from one rule.
        slots = await call(
            "create_timeslot",
            {"season_id": season_id, "start": "18:40", "interval": 50, "count": 3},
        )
        assert slots["times"] == DEMO_SLOTS

        # 3. The Christmas break.
        await call(
            "add_season_exclusion_dates", {"season_id": season_id, "dates": DEMO_BREAK}
        )

        # 4. Divisions, their two stages, and their teams.
        divisions = []
        for title, count in DEMO_DIVISIONS:
            division = await call(
                "create_division",
                {
                    "season_id": season_id,
                    "title": title,
                    "points_formula": "3*win + 2*draw + 1*loss",
                    "forfeit_for_score": 5,
                    "forfeit_against_score": 0,
                },
            )
            division_id = division["division"]["id"]
            regular = await call(
                "create_stage", {"division_id": division_id, "title": "Regular Season"}
            )
            finals = await call(
                "create_stage",
                {"division_id": division_id, "title": "Finals", "keep_ladder": False},
            )
            for n in range(1, count + 1):
                await call(
                    "create_team",
                    {
                        "division_id": division_id,
                        "title": f"{title} {n}",
                        "verbose": False,
                    },
                )
            divisions.append(
                {
                    "id": division_id,
                    "teams": count,
                    "regular": regular["stage"]["id"],
                    "finals": finals["stage"]["id"],
                }
            )

        # 5. Draw formats, created only if they are missing.
        formats = await call("list_draw_formats", {})
        by_name = {f["name"]: f["id"] for f in formats["draw_formats"]}
        wanted = {
            f"Round Robin ({n} teams)": (round_robin_format(n), n, False)
            for n in sorted({count for __, count in DEMO_DIVISIONS})
        }
        wanted["Top 4 finals"] = (DEMO_FINALS, 4, True)
        for name, (text, teams, is_final) in wanted.items():
            if name not in by_name:
                created = await call(
                    "create_draw_format",
                    {"name": name, "text": text, "teams": teams, "is_final": is_final},
                )
                by_name[name] = created["draw_format"]["id"]

        # 6. The regular seasons: checked with a dry run, then built.
        regular = [
            {
                "stage_id": d["regular"],
                "draw_format_id": by_name[f"Round Robin ({d['teams']} teams)"],
                "start_date": DEMO_START,
                "rounds": 12,
            }
            for d in divisions
        ]
        plan = await call("build_draw", {"builds": regular, "dry_run": True})
        assert plan["matches"] == 144
        built = await call("build_draw", {"builds": regular, "verbose": True})
        assert built["matches"] == 144

        # 7. The finals, from the semi-final date.
        finals = await call(
            "build_draw",
            {
                "builds": [
                    {
                        "stage_id": d["finals"],
                        "draw_format_id": by_name["Top 4 finals"],
                        "start_date": DEMO_SEMIS,
                    }
                    for d in divisions
                ],
                "verbose": True,
            },
        )

        # 8. A ground and a time for every match: each night's matches take
        # the slots in turn, every ground at the first slot first.
        rows = [row for b in built["builds"] + finals["builds"] for row in b["rows"]]
        by_date = {}
        for row in rows:
            by_date.setdefault(row["date"], []).append(row["id"])
        cells = [(time, ground) for time in DEMO_SLOTS for ground in grounds]
        items = [
            {"match_id": match_id, "time": time, "place_id": ground}
            for date in sorted(by_date)
            for match_id, (time, ground) in zip(by_date[date], cells)
        ]
        assert len(items) == len(rows) == 153
        scheduled = await call("schedule_matches", {"items": items})
        assert scheduled["saved"] == 153

    return {
        "season_id": season_id,
        "divisions": divisions,
        "plan": plan,
        "built": built,
        "finals": finals,
        "calls": calls,
    }


def test_demo_competition_within_budget(live_server, admin_user):
    """
    Purpose: rebuild the demo competition (three divisions of 8, 6 and 10
    teams, one venue with four grounds, three weeknight time slots, a
    12-round weekly regular season with a Christmas break, then semis and
    a final) through the MCP client, as an agent would, and check the
    result is a sound, fully scheduled draw.

    Prerequisites: a superuser who authorises the client.

    Expected behaviour: the draw is configured and built with a handful of
    calls (time slots, exclusions, formats, ``build_draw``,
    ``schedule_matches``) instead of one ``create_match`` per match; every
    pairing is played, no team plays twice in a night, no ground is double
    booked, no match falls on an excluded date or outside a time slot, the
    finals are wired to ladder positions and semi winners, and once the
    regular season has been played the semis evaluate to the top four.

    Limitations: competitions, seasons, venues, grounds, divisions, stages
    and teams are still created one call per record, so the call budget is
    asserted for the rest of the workflow, with the total bounded by the
    two together.
    """
    person = Person(live_server.url, "admin", "password")
    demo = run(build_demo, live_server, person)

    calls = demo["calls"]
    record_calls = [
        c
        for c in calls
        if c
        in {
            "create_competition",
            "create_season",
            "create_venue",
            "create_ground",
            "create_division",
            "create_stage",
            "create_team",
        }
    ]
    assert len(record_calls) == DEMO_RECORD_CALLS
    assert len(calls) - len(record_calls) <= DEMO_WORKFLOW_BUDGET, calls
    assert calls.count("build_draw") == 3
    assert calls.count("schedule_matches") == 1
    assert "create_match" not in calls and "reschedule_match" not in calls

    # The dry run planned exactly what was then built.
    def without_ids(row):
        return {k: v for k, v in row.items() if k != "id"}

    assert [b["rows"] for b in demo["plan"]["builds"]] == [
        [without_ids(row) for row in b["rows"]] for b in demo["built"]["builds"]
    ]

    season = Season.objects.get(pk=demo["season_id"])
    matches = Match.objects.filter(stage__division__season=season)
    assert matches.count() == 153
    excluded = {datetime.date.fromisoformat(d) for d in DEMO_BREAK}
    slots = {datetime.time.fromisoformat(t) for t in DEMO_SLOTS}

    # Every pairing at least once in each division's regular season.
    for division in demo["divisions"]:
        regular = matches.filter(stage_id=division["regular"])
        pairings = {frozenset((m.home_team_id, m.away_team_id)) for m in regular}
        teams = division["teams"]
        assert len(pairings) == teams * (teams - 1) // 2
        assert regular.filter(is_bye=True).count() == 0

    # No team twice on one date, no ground or time clash, no excluded date
    # and every time a slot.
    teams_by_date = {}
    places = set()
    for match in matches:
        assert match.date not in excluded
        assert match.time in slots
        assert match.play_at_id is not None
        assert match.datetime is not None
        key = (match.date, match.time, match.play_at_id)
        assert key not in places
        places.add(key)
        for team_id in (match.home_team_id, match.away_team_id):
            if team_id is None:
                continue
            assert (match.date, team_id) not in teams_by_date
            teams_by_date[(match.date, team_id)] = match.pk
    assert sorted({m.date for m in matches})[-2:] == [
        datetime.date(2027, 1, 20),
        datetime.date(2027, 1, 27),
    ]

    # Finals are wired to the ladder and the semi winners.
    for division in demo["divisions"]:
        semi_1, semi_2, final = Match.objects.filter(
            stage_id=division["finals"]
        ).order_by("round", "pk")
        assert (semi_1.home_team_eval, semi_1.away_team_eval) == ("P1", "P4")
        assert (semi_2.home_team_eval, semi_2.away_team_eval) == ("P2", "P3")
        assert (final.home_team_eval, final.home_team_eval_related_id) == (
            "W",
            semi_1.pk,
        )
        assert (final.away_team_eval, final.away_team_eval_related_id) == (
            "W",
            semi_2.pk,
        )

    # Play the regular season (the team entered earlier always wins) and
    # the semis evaluate to the top four of the ladder.
    admin = AdminToolset(request=SimpleNamespace(user=admin_user))
    for division in demo["divisions"]:
        regular = Stage.objects.get(pk=division["regular"])
        order = {t.pk: t.order for t in regular.division.teams.all()}
        for match in regular.matches.all():
            home_wins = order[match.home_team_id] < order[match.away_team_id]
            admin.record_match_result(
                match.pk,
                home_team_score=5 if home_wins else 1,
                away_team_score=1 if home_wins else 5,
                verbose=False,
            )
        ladder = admin.get_ladder(stage_id=regular.pk)["stages"][0]["pools"][0]
        top = [entry["team"]["id"] for entry in ladder["ladder"][:4]]
        assert top[0] == regular.division.teams.get(order=1).pk
        semi_1, semi_2, __ = Match.objects.filter(stage_id=division["finals"]).order_by(
            "round", "pk"
        )
        assert semi_1.eval(lazy=True) == (top[0], top[3])
        assert semi_2.eval(lazy=True) == (top[1], top[2])
