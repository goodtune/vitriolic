"""
Test doubles for the MySideline HTTP boundary.

Shared by the unit tests and the end-to-end tests so that both can drive
the real client and reconciler against captured responses without
touching the live site.
"""

import json
import os

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "mysideline")

# Association 299999 is the NSW State Cup; its 2025 competitions were
# captured in full (21 competitions, ~950 matches) as a representative
# sample of a complete, pooled, finals-bearing tournament.
STATE_CUP_URL = "https://tfa.mysideline.com.au/competitions/association/299999"
STATE_CUP_SEASON = 2025


class FakeResponse:
    def __init__(self, status_code=200, text="", content_type="application/json"):
        self.status_code = status_code
        self.text = text
        self.headers = {"Content-Type": content_type}

    def json(self):
        return json.loads(self.text)


class FakeSession:
    """
    Minimal stand-in for ``requests.Session``: routes requests to handlers
    keyed by URL, records every call and can be told to fail.
    """

    def __init__(self):
        self.headers = {}
        self.handlers = {}
        self.default = None
        self.calls = []
        self.exception = None

    def mount(self, prefix, adapter):
        pass

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.exception is not None:
            raise self.exception
        handler = self.handlers.get(url, self.default)
        if handler is None:
            raise KeyError(url)
        return handler(method, url, kwargs)


def fixture(*parts):
    with open(os.path.join(FIXTURES, *parts)) as fp:
        return fp.read()


def rsc_line(payload) -> str:
    """Render ``payload`` as one line of a React Server Component payload."""
    return '1:"$Sreact.fragment"\n7:%s\n' % json.dumps(["$", "$L13", None, payload])


def state_cup_session():
    """
    A :class:`FakeSession` serving the captured NSW State Cup 2025 data.
    """
    from tournamentcontrol.competition.mysideline.client import GRAPHQL_ENDPOINT

    session = FakeSession()
    listing = fixture("state_cup_2025", "association.rsc")
    session.handlers[STATE_CUP_URL] = lambda method, url, kwargs: FakeResponse(
        text=listing, content_type="text/x-component"
    )

    def competition_page(competition_id):
        # The captured page payload is reduced to the settings the client
        # reads from it (see ``competition_65396575.rsc`` for a full page).
        settings = json.loads(
            fixture("state_cup_2025", "competition_%d_settings.json" % competition_id)
        )
        return lambda method, url, kwargs: FakeResponse(
            text=rsc_line({"data": {"competition": settings}}),
            content_type="text/x-component",
        )

    for name in os.listdir(os.path.join(FIXTURES, "state_cup_2025")):
        if name.endswith("_settings.json"):
            competition_id = int(name.split("_")[1])
            session.handlers[
                "https://tfa.mysideline.com.au/competitions/%d" % competition_id
            ] = competition_page(competition_id)

    def graphql(method, url, kwargs):
        body = kwargs["json"]
        competition_id = body["variables"]["competitionId"]
        kind = "matches" if "competitionMatches" in body["query"] else "teams"
        return FakeResponse(
            text=fixture(
                "state_cup_2025", "competition_%d_%s.json" % (competition_id, kind)
            )
        )

    session.handlers[GRAPHQL_ENDPOINT] = graphql
    return session
