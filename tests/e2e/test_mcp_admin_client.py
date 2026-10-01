"""
End-to-end tests driving the competition *administration* MCP server with
the official MCP client, including the OAuth 2.1 flow the client runs to
obtain a bearer token: discovery from the 401 challenge, dynamic client
registration, authorization in the "browser" with PKCE, and the token
exchange.
"""

import asyncio
import threading
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx2
import pytest
import requests
from mcp.client import Client
from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientMetadata

from tournamentcontrol.competition.tests import factories

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
