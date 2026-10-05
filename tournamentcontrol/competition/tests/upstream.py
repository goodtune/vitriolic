"""
Test doubles for the HTTP boundary of the upstream backends.

Shared by the unit tests and the end-to-end tests so that both can drive
the real clients and reconciler against captured responses without
touching the live sites.
"""

import json
import re
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

from tournamentcontrol.competition.upstream.backends.mysideline import (
    GRAPHQL_ENDPOINT,
)

FIXTURES = Path(__file__).parent / "fixtures" / "mysideline"
REVOLUTIONISE_FIXTURES = Path(__file__).parent / "fixtures" / "revolutionise"

# Association 299999 is the NSW State Cup; its 2025 competitions were
# captured in full (21 competitions, ~950 matches) as a representative
# sample of a complete, pooled, finals-bearing tournament.
STATE_CUP_URL = "https://tfa.mysideline.com.au/competitions/association/299999"
STATE_CUP_SEASON = 2025
STATE_CUP_SEASON_URL = urlunsplit(
    urlsplit(STATE_CUP_URL)._replace(query=urlencode({"season": STATE_CUP_SEASON}))
)

# Central Coast Hockey Association on revolutioniseSPORT; its 2026 Mens
# competition (three grades, 23 rounds including finals, byes and a forfeit)
# was captured in full from the public pages.
CCHA_URL = "https://www.revolutionise.com.au/ccha/games"
CCHA_MENS_URL = "https://www.revolutionise.com.au/ccha/games/25527"


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
    return FIXTURES.joinpath(*parts).read_text()


def rsc_line(payload) -> str:
    """Render ``payload`` as one line of a React Server Component payload."""
    body = json.dumps(["$", "$L13", None, payload])
    return f'1:"$Sreact.fragment"\n7:{body}\n'


def state_cup_session(renames=None):
    """
    A :class:`FakeSession` serving the captured NSW State Cup 2025 data.

    ``renames`` maps a name as captured to the name MySideline should
    publish instead, so that a test can play back an upstream rename of a
    competition or a team without needing a second capture. Names are
    replaced in their JSON-quoted form, so a name which happens to be a
    substring of another value is not touched.
    """

    def rename(text):
        for before, after in (renames or {}).items():
            text = text.replace(json.dumps(before), json.dumps(after))
        return text

    session = FakeSession()
    listing = rename(fixture("state_cup_2025", "association.rsc"))
    session.handlers[STATE_CUP_URL] = lambda method, url, kwargs: FakeResponse(
        text=listing, content_type="text/x-component"
    )

    def competition_page(competition_id):
        # The captured page payload is reduced to the settings the client
        # reads from it (see ``competition_65396575.rsc`` for a full page).
        settings = json.loads(
            fixture("state_cup_2025", f"competition_{competition_id}_settings.json")
        )
        return lambda method, url, kwargs: FakeResponse(
            text=rsc_line({"data": {"competition": settings}}),
            content_type="text/x-component",
        )

    for path in (FIXTURES / "state_cup_2025").glob("competition_*_settings.json"):
        competition_id = int(path.name.split("_")[1])
        session.handlers[
            urlunsplit(
                urlsplit(STATE_CUP_URL)._replace(path=f"/competitions/{competition_id}")
            )
        ] = competition_page(competition_id)

    def graphql(method, url, kwargs):
        body = kwargs["json"]
        competition_id = body["variables"]["competitionId"]
        kind = "matches" if "competitionMatches" in body["query"] else "teams"
        return FakeResponse(
            text=rename(
                fixture("state_cup_2025", f"competition_{competition_id}_{kind}.json")
            )
        )

    session.handlers[GRAPHQL_ENDPOINT] = graphql
    return session


def ccha_session(renames=None):
    """
    A :class:`FakeSession` serving the captured Central Coast Hockey pages.

    Every page under ``fixtures/revolutionise`` is served at the URL its
    file name encodes; see ``capture.txt`` there for the mapping. ``renames``
    substitutes names in the served HTML, as :func:`state_cup_session` does,
    to play back an upstream rename.
    """

    def rename(text):
        for before, after in (renames or {}).items():
            text = re.sub(rf"(?<!\w){re.escape(before)}(?!\w)", after, text)
        return text

    session = FakeSession()
    for line in (REVOLUTIONISE_FIXTURES / "capture.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, url = line.split(None, 1)
        text = (REVOLUTIONISE_FIXTURES / name).read_text()
        content_type = (
            "text/calendar; charset=utf-8"
            if name.endswith(".ics")
            else "text/html; charset=utf-8"
        )
        session.handlers[url] = (
            lambda method, url, kwargs, text=text, content_type=content_type: (
                FakeResponse(text=rename(text), content_type=content_type)
            )
        )

    def missing(method, url, kwargs):
        return FakeResponse(status_code=404, text="", content_type="text/html")

    session.default = missing
    return session
