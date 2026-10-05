"""
MySideline (Touch Football Australia / NRL).

MySideline is the competition management platform used by Touch Football
Australia. The public competition website (``https://tfa.mysideline.com.au``)
is a Next.js application that reads from a public GraphQL API operated by the
NRL. Two remote interfaces are used, both anonymous and read-only:

1. **GraphQL** (``https://community-backend.api.nationalrugbyleague.io/graphql``)
   is the API the MySideline frontend calls from the browser. It exposes
   ``competitionMatches``, ``competitionLadder`` and ``teams`` queries which
   give the complete draw, results, team list and pool membership for a
   competition identified by its integer id.

2. The **association page** (``/competitions/association/<id>``) is rendered
   server-side by Next.js. There is no GraphQL query that lists competitions
   by association, so the list is read from the React Server Component
   payload that the page embeds. Requesting the page with an ``RSC: 1``
   header returns just the payload (``text/x-component``); the same payload
   is also embedded in the HTML in ``self.__next_f.push`` calls, which is
   used as a fallback.

Mapping onto Vitriolic: an association is a ``Competition``, a year (and
optionally a half-year period) of the association is a ``Season``, and each
MySideline competition is a ``Division``. See ``docs/mysideline.md``.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from pydantic import BaseModel, ConfigDict, Field

from tournamentcontrol.competition.upstream.base import (
    HttpClient,
    BaseUpstreamBackend,
    UpstreamResponseError,
    UpstreamURLError,
)
from tournamentcontrol.competition.upstream.types import (
    STATUS_PRE_GAME,
    RemoteCompetition,
    RemoteLadderTemplate,
    RemoteMatch,
    RemoteTeam,
    RemoteVenue,
)

logger = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://community-backend.api.nationalrugbyleague.io/graphql"

NationalId = Literal["TFA", "PRL"]

# Map the MySideline host to the ``nationalId`` GraphQL enum. Touch Football
# Australia is the only sport currently supported; anything else is PRL.
NATIONAL_ID_BY_HOST_PREFIX: dict[str, NationalId] = {
    "tfa": "TFA",
}

# MySideline splits each calendar year into two periods ("seasonTag"):
# winter competitions carry tag 1, summer/spring competitions carry tag 2.
SEASON_TAGS = {1: "First half (winter)", 2: "Second half (summer)"}

ASSOCIATION_PATH_RE = re.compile(r"^/competitions/association/(?P<id>\d+)/?$")
COMPETITION_PATH_RE = re.compile(r"^/competitions/(?P<id>\d+)/?$")
NEXT_FLIGHT_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.DOTALL)

COMPETITION_MATCHES_QUERY = """
query CompetitionMatches($competitionId: Int!) {
  competitionMatches(competitionId: $competitionId) {
    _id
    status
    dateTime
    round { number type displayName }
    homeTeam { _id name }
    awayTeam { _id name }
    scores { homeTeam awayTeam }
    meta { isTba isBye fieldNo forfeitingTeam { _id name } }
    venue { _id name venueTimezone }
    fullVenue { address { lat lng } }
  }
}
"""

COMPETITION_TEAMS_QUERY = """
query CompetitionTeams($competitionId: Int!, $seasonId: Int!, $nationalId: NationalId!) {
  teams(seasonId: $seasonId, nationalId: $nationalId, competitionId: $competitionId) {
    _id
    name
  }
  competitionLadder(competitionId: $competitionId) {
    teams { _id name pool }
  }
}
"""


class RemoteCompetitionSummary(BaseModel):
    """A competition as listed on an association page."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    season: int
    season_tag: Optional[int] = None
    is_active: bool = True


class RemoteAssociation(BaseModel):
    """The competitions belonging to an association."""

    model_config = ConfigDict(frozen=True)

    id: int
    competitions: tuple[RemoteCompetitionSummary, ...] = Field(default_factory=tuple)


class MySidelineURL:
    """
    A parsed MySideline URL.

    An association URL may carry the ``season`` and ``seasonTag`` query
    parameters the site itself adds when its *Year* and period drop-downs
    are used; they select which of the association's competitions a season
    mirrors.
    """

    def __init__(self, url: str):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise UpstreamURLError("Not an absolute http(s) URL: %r" % url)
        host = parsed.netloc.lower()
        if not host.endswith(".mysideline.com.au"):
            raise UpstreamURLError("Not a mysideline.com.au URL: %r" % url)

        self.host = host
        self.association_id: Optional[int] = None
        self.competition_id: Optional[int] = None
        self.season: Optional[int] = None
        self.season_tag: Optional[int] = None

        query = parse_qs(parsed.query)
        self.season = _int((query.get("season") or [None])[0])
        self.season_tag = _int((query.get("seasonTag") or [None])[0])

        match = ASSOCIATION_PATH_RE.match(parsed.path)
        if match:
            self.association_id = int(match.group("id"))
            return
        match = COMPETITION_PATH_RE.match(parsed.path)
        if match:
            self.competition_id = int(match.group("id"))
            return
        raise UpstreamURLError(
            "Expected an association or competition URL such as "
            "https://tfa.mysideline.com.au/competitions/association/6338, "
            "got %r" % url
        )

    @property
    def national_id(self) -> NationalId:
        prefix = self.host.split(".", 1)[0]
        return NATIONAL_ID_BY_HOST_PREFIX.get(prefix, "PRL")

    @property
    def canonical(self) -> str:
        """The association or competition page, without any filter."""
        if self.association_id is not None:
            return "https://%s/competitions/association/%d" % (
                self.host,
                self.association_id,
            )
        return "https://%s/competitions/%d" % (self.host, self.competition_id)

    @property
    def season_url(self) -> str:
        """The association page filtered to the season and period."""
        params = {}
        if self.season is not None:
            params["season"] = self.season
        if self.season_tag is not None:
            params["seasonTag"] = self.season_tag
        if params:
            return "%s?%s" % (self.canonical, urlencode(params))
        return self.canonical

    def competition_url(self, competition_id: int) -> str:
        return "https://%s/competitions/%d" % (self.host, competition_id)


def _int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _epoch_ms(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _str(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


class MySidelineClient(HttpClient):
    """
    Thin client over the two MySideline interfaces.

    All public methods raise :class:`UpstreamTransportError` when the network
    or HTTP layer fails, and :class:`UpstreamResponseError` when a response
    cannot be understood. They never return partial data.
    """

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout=None,
        graphql_endpoint: str = GRAPHQL_ENDPOINT,
    ):
        super().__init__(session=session, timeout=timeout)
        self.graphql_endpoint = graphql_endpoint

    def graphql(self, query: str, variables: dict) -> dict:
        response = self.request(
            "POST",
            self.graphql_endpoint,
            json={"query": query, "variables": variables},
            headers={"Accept": "application/json"},
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstreamResponseError("GraphQL response is not JSON") from exc
        if not isinstance(payload, dict):
            raise UpstreamResponseError("GraphQL response is not an object")
        if payload.get("errors"):
            messages = [
                str(error.get("message", error))
                for error in payload["errors"]
                if isinstance(error, dict)
            ]
            raise UpstreamResponseError("GraphQL errors: %s" % "; ".join(messages))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise UpstreamResponseError("GraphQL response has no data")
        return data

    # -- association listing ---------------------------------------------

    def get_association(self, url: MySidelineURL) -> RemoteAssociation:
        if url.association_id is None:
            raise UpstreamURLError("Not an association URL: %s" % url.canonical)
        response = self.request(
            "GET",
            url.canonical,
            headers={"RSC": "1", "Accept": "text/x-component, text/html"},
        )
        content_type = response.headers.get("Content-Type", "")
        if "text/x-component" in content_type:
            data = _find_flight_data(response.text.splitlines(), "competitions")
        else:
            data = _find_flight_data(
                _flight_lines_from_html(response.text), "competitions"
            )
        if data is None:
            raise UpstreamResponseError(
                "Association page did not contain a competition listing"
            )
        competitions = []
        for raw in data["competitions"]:
            if not isinstance(raw, dict):
                raise UpstreamResponseError("Competition entry is not an object")
            competition_id = _int(raw.get("_id"))
            name = _str(raw.get("name"))
            season = _int(raw.get("season"))
            if competition_id is None or name is None or season is None:
                raise UpstreamResponseError(
                    "Competition entry missing id, name or season: %r" % raw
                )
            competitions.append(
                RemoteCompetitionSummary(
                    id=competition_id,
                    name=name,
                    season=season,
                    season_tag=_int(raw.get("seasonTag")),
                    is_active=bool(raw.get("isActive", True)),
                )
            )
        return RemoteAssociation(
            id=url.association_id, competitions=tuple(competitions)
        )

    # -- competition settings --------------------------------------------

    def get_ladder_template(
        self, url: MySidelineURL, competition_id: int
    ) -> RemoteLadderTemplate:
        """
        The ladder points scheme of a competition.

        Not exposed by GraphQL for a single competition, so it is read from
        the competition page's server component payload in the same way as
        the association listing.
        """
        response = self.request(
            "GET",
            url.competition_url(competition_id),
            headers={"RSC": "1", "Accept": "text/x-component, text/html"},
        )
        content_type = response.headers.get("Content-Type", "")
        if "text/x-component" in content_type:
            lines = response.text.splitlines()
        else:
            lines = _flight_lines_from_html(response.text)
        data = _find_flight_object(lines, "laddertemplate")
        if data is None:
            raise UpstreamResponseError(
                "Competition page did not contain a ladder template"
            )
        raw = data["laddertemplate"]
        if not isinstance(raw, dict):
            raise UpstreamResponseError("laddertemplate is not an object")
        defaults = RemoteLadderTemplate()
        return RemoteLadderTemplate(
            name=_str(raw.get("name")),
            points_win=_int_or(raw.get("pointsWin"), defaults.points_win),
            points_draw=_int_or(raw.get("pointsDraw"), defaults.points_draw),
            points_loss=_int_or(raw.get("pointsLoss"), defaults.points_loss),
            points_bye=_int_or(raw.get("pointsBye"), defaults.points_bye),
            points_forfeit_for=_int_or(
                raw.get("pointsFF"), defaults.points_forfeit_for
            ),
            forfeit_score=_int_or(
                raw.get("defaultScoreFFReceived"), defaults.forfeit_score
            ),
            forfeit_counts_as_played=bool(raw.get("ffCountAsPlayed", True)),
        )

    # -- competition detail ----------------------------------------------

    def get_competition(
        self,
        competition_id: int,
        name: str,
        season: int,
        national_id: NationalId,
        ladder_template: Optional[RemoteLadderTemplate] = None,
    ) -> RemoteCompetition:
        variables = {
            "competitionId": competition_id,
            "seasonId": season,
            "nationalId": national_id,
        }
        teams_data = self.graphql(COMPETITION_TEAMS_QUERY, variables)
        matches_data = self.graphql(
            COMPETITION_MATCHES_QUERY, {"competitionId": competition_id}
        )

        raw_teams = teams_data.get("teams")
        if raw_teams is None:
            raw_teams = []
        if not isinstance(raw_teams, list):
            raise UpstreamResponseError("teams is not a list")

        ladder = teams_data.get("competitionLadder") or {}
        if not isinstance(ladder, dict):
            raise UpstreamResponseError("competitionLadder is not an object")
        raw_ladder_teams = ladder.get("teams") or []
        if not isinstance(raw_ladder_teams, list):
            raise UpstreamResponseError("competitionLadder.teams is not a list")

        raw_matches = matches_data.get("competitionMatches")
        if raw_matches is None:
            raw_matches = []
        if not isinstance(raw_matches, list):
            raise UpstreamResponseError("competitionMatches is not a list")

        # Teams: the ``teams`` query is canonical for the team list, the
        # ladder supplies pool membership, and any team referenced by a
        # fixture but missing from both (eg. withdrawn) is still included so
        # that its matches can be represented.
        teams: dict[int, dict] = {}
        for raw in raw_teams:
            team_id, team_name = _int(raw.get("_id")), _str(raw.get("name"))
            if team_id is None or team_name is None:
                raise UpstreamResponseError("Team entry missing id or name")
            teams[team_id] = {"id": team_id, "name": team_name, "pool": None}
        for raw in raw_ladder_teams:
            team_id, team_name = _int(raw.get("_id")), _str(raw.get("name"))
            if team_id is None or team_name is None:
                raise UpstreamResponseError("Ladder team entry missing id or name")
            entry = teams.setdefault(
                team_id, {"id": team_id, "name": team_name, "pool": None}
            )
            entry["pool"] = _str(raw.get("pool"))

        matches = []
        for raw in raw_matches:
            match = _parse_match(raw)
            matches.append(match)
            for side in ("homeTeam", "awayTeam"):
                team = raw.get(side) or {}
                team_id, team_name = _int(team.get("_id")), _str(team.get("name"))
                if team_id is not None and team_name is not None:
                    teams.setdefault(
                        team_id, {"id": team_id, "name": team_name, "pool": None}
                    )

        return RemoteCompetition(
            id=competition_id,
            name=name,
            teams=tuple(RemoteTeam(**team) for team in teams.values()),
            matches=tuple(matches),
            ladder_template=ladder_template,
        )


def _parse_match(raw: Any) -> RemoteMatch:
    if not isinstance(raw, dict):
        raise UpstreamResponseError("Match entry is not an object")
    match_id = _int(raw.get("_id"))
    if match_id is None:
        raise UpstreamResponseError("Match entry missing id: %r" % raw)
    round_ = raw.get("round") or {}
    if not isinstance(round_, dict):
        raise UpstreamResponseError("Match round is not an object")
    round_number = _int(round_.get("number"))
    round_type = _str(round_.get("type"))
    round_name = _str(round_.get("displayName"))
    if round_number is None or round_type is None:
        raise UpstreamResponseError("Match %d has no round detail" % match_id)

    meta = raw.get("meta") or {}
    scores = raw.get("scores") or {}
    home = raw.get("homeTeam") or {}
    away = raw.get("awayTeam") or {}
    forfeiting = meta.get("forfeitingTeam") or {}
    # Status is usually lower case but "Final" has been observed on byes;
    # normalise so the reconciler only ever sees one spelling.
    status = (_str(raw.get("status")) or STATUS_PRE_GAME).lower()

    venue = None
    raw_venue = raw.get("venue") or {}
    venue_id, venue_name = _int(raw_venue.get("_id")), _str(raw_venue.get("name"))
    if venue_id is not None and venue_name is not None:
        address = (raw.get("fullVenue") or {}).get("address") or {}
        venue = RemoteVenue(
            id=venue_id,
            name=venue_name,
            timezone=_str(raw_venue.get("venueTimezone")),
            latitude=_float(address.get("lat")),
            longitude=_float(address.get("lng")),
        )

    return RemoteMatch(
        id=match_id,
        round_number=round_number,
        round_type=round_type,
        round_name=round_name or "Round %d" % round_number,
        start=_epoch_ms(raw.get("dateTime")),
        status=status,
        home_team_id=_int(home.get("_id")),
        away_team_id=_int(away.get("_id")),
        home_score=_int(scores.get("homeTeam")),
        away_score=_int(scores.get("awayTeam")),
        is_bye=bool(meta.get("isBye", False)),
        is_tba=bool(meta.get("isTba", False)),
        forfeiting_team_id=_int(forfeiting.get("_id")),
        venue=venue,
        field=_str(meta.get("fieldNo")),
    )


def _int_or(value: Any, default: int) -> int:
    parsed = _int(value)
    return default if parsed is None else parsed


def _float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _flight_lines_from_html(html: str) -> list[str]:
    """
    Extract the React Server Component payload embedded in a Next.js page.

    Next.js streams the payload to the client as a series of
    ``self.__next_f.push([1, "<chunk>"])`` script calls; concatenating the
    chunks (after unescaping the JavaScript string literal) yields the same
    line-oriented payload that an ``RSC: 1`` request returns directly.
    """
    chunks = NEXT_FLIGHT_PUSH_RE.findall(html)
    text = "".join(json.loads('"%s"' % chunk) for chunk in chunks)
    return text.splitlines()


def _find_flight_data(lines, key: str) -> Optional[dict]:
    """
    Search each ``<id>:<json>`` line of a flight payload for the first JSON
    object containing ``key`` mapped to a list, and return that object.
    """
    return _find_flight(lines, key, list)


def _find_flight_object(lines, key: str) -> Optional[dict]:
    """As :func:`_find_flight_data` but ``key`` must map to an object."""
    return _find_flight(lines, key, dict)


def _find_flight(lines, key: str, kind) -> Optional[dict]:
    for line in lines:
        _, sep, body = line.partition(":")
        if not sep:
            continue
        try:
            value = json.loads(body)
        except ValueError:
            continue
        found = _walk(value, key, kind)
        if found is not None:
            return found
    return None


def _walk(value, key: str, kind) -> Optional[dict]:
    if isinstance(value, dict):
        if isinstance(value.get(key), kind):
            return value
        for child in value.values():
            found = _walk(child, key, kind)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _walk(child, key, kind)
            if found is not None:
                return found
    return None


def select_competitions(
    season: Optional[int], season_tag: Optional[int], competitions
) -> list[RemoteCompetitionSummary]:
    """
    Apply a season URL's ``season`` / ``seasonTag`` filters to an
    association's competition listing.

    The association page lists every competition the association has ever
    published; its "Year" and period drop-downs are client-side filters on
    the same ``season`` and ``seasonTag`` values used here.
    """
    selected = []
    for competition in competitions:
        if competition.season != season:
            continue
        if season_tag is not None and competition.season_tag != season_tag:
            continue
        selected.append(competition)
    return selected


class MySidelineBackend(BaseUpstreamBackend):
    key = "mysideline"
    name = "MySideline"
    competition_url_example = (
        "https://tfa.mysideline.com.au/competitions/association/6338"
    )
    season_url_example = (
        "https://tfa.mysideline.com.au/competitions/association/6338"
        "?season=2026&seasonTag=2"
    )

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host == "mysideline.com.au" or host.endswith(".mysideline.com.au")

    def parse_competition_url(self, url: str) -> str:
        parsed = MySidelineURL(url)
        if parsed.association_id is None:
            raise UpstreamURLError(
                "Enter the MySideline association URL, for example %s"
                % self.competition_url_example
            )
        return parsed.canonical

    def parse_season_url(self, url: str, competition_url: str) -> str:
        parsed = MySidelineURL(url)
        association = MySidelineURL(competition_url)
        if parsed.association_id is None or (
            parsed.association_id != association.association_id
            or parsed.host != association.host
        ):
            raise UpstreamURLError(
                "Enter the competition's association page filtered to the "
                "season, for example %s" % self.season_url_example
            )
        if parsed.season is None:
            raise UpstreamURLError(
                "The URL must select a season: pick the year from the Year "
                "drop-down on the association page and copy the address, for "
                "example %s" % self.season_url_example
            )
        if parsed.season_tag is not None and parsed.season_tag not in SEASON_TAGS:
            raise UpstreamURLError(
                "seasonTag must be 1 (first half of the year) or 2 (second half)"
            )
        return parsed.season_url

    def new_client(self, session: Optional[requests.Session] = None):
        return MySidelineClient(session=session)

    def fetch_snapshot(self, season, client=None) -> list[RemoteCompetition]:
        if client is None:
            client = self.new_client()
        url = MySidelineURL(season.upstream_url)
        association = client.get_association(url)
        snapshots = []
        for summary in select_competitions(
            url.season, url.season_tag, association.competitions
        ):
            # The ladder template only seeds newly created divisions, so a
            # change in the (less stable) page payload must not block the
            # sync of draws and results; transport failures still abort.
            try:
                ladder_template = client.get_ladder_template(url, summary.id)
            except UpstreamResponseError as exc:
                logger.warning(
                    "Ladder template for MySideline competition %d unavailable: %s",
                    summary.id,
                    exc,
                )
                ladder_template = None
            snapshots.append(
                client.get_competition(
                    summary.id,
                    summary.name,
                    summary.season,
                    url.national_id,
                    ladder_template=ladder_template,
                )
            )
        return snapshots
