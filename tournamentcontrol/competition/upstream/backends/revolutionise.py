"""
revolutioniseSPORT (``https://www.revolutionise.com.au``).

revolutioniseSPORT is a hosted club and association management platform.
Each organisation ("tenant") has a public site under
``https://www.revolutionise.com.au/<slug>/`` whose *Draws & results* module
publishes competitions, grades, rounds, fixtures, results and ladders.
Unlike MySideline there is no public API behind the pages: the site is
rendered server-side (a Laravel application; the pages are plain Bootstrap
HTML without a data layer), content negotiation for JSON is refused, and the
only machine-readable export is a per-team iCalendar feed that carries no
results. The pages are therefore scraped. See ``docs/revolutionise.md`` for
what each page provides and how the gaps are filled.

Pages used (``<slug>`` is the organisation, eg. ``ccha``):

``/<slug>/games``
    The index: every competition currently published with its grades.
``/<slug>/games/<competition>/<grade>``
    The rounds of a grade, with a *View ladder* link when it keeps one.
``/<slug>/games/<competition>/<grade>/round/<n>``
    The fixtures of a round: date, time, venue, field, teams, score or
    ``vs``, forfeit badges, umpires and a link to the game, followed by the
    teams with a bye.
``/<slug>/pointscore/<competition>/<grade>``
    The ladder: the team list (including teams yet to play) and the totals
    from which the points scheme is inferred.
``/<slug>/games/team/export/ical/<competition>/<team>``
    A team's fixtures as iCalendar; read once per competition for its
    ``TZID``, which is the only place the site states a time zone.
``/<slug>/game/<id>``
    A fixture's page, read once per venue for the venue's address and the
    coordinates in its embedded map.

Mapping onto Vitriolic: the organisation is a ``Competition``, a
revolutioniseSPORT competition (or the whole index) is a ``Season``, and each
grade is a ``Division``. Identifiers are ``<competition>/<grade>`` for a
grade (grade ids are reused across the organisation's competitions), the
team id for a team and the game id for a fixture.
"""

import itertools
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from bs4 import BeautifulSoup

from tournamentcontrol.competition.upstream.base import (
    HttpClient,
    UpstreamError,
    BaseUpstreamBackend,
    UpstreamResponseError,
    UpstreamURLError,
)
from tournamentcontrol.competition.upstream.types import (
    ROUND_FINAL,
    ROUND_REGULAR,
    STATUS_FINAL,
    STATUS_FORFEIT,
    STATUS_PRE_GAME,
    RemoteCompetition,
    RemoteLadderTemplate,
    RemoteMatch,
    RemoteTeam,
    RemoteVenue,
)

logger = logging.getLogger(__name__)

HOSTS = ("www.revolutionise.com.au", "revolutionise.com.au")
BASE = "https://www.revolutionise.com.au"

GRADE_PATH_RE = re.compile(r"/games/(?P<competition>\d+)/(?P<grade>\d+)/?$")
ROUND_PATH_RE = re.compile(r"/games/\d+/\d+/round/(?P<number>\d+)/?$")
TEAM_PATH_RE = re.compile(r"/games/team/(?P<competition>\d+)/(?P<team>\d+)/?$")
VENUE_PATH_RE = re.compile(r"/venues/(?P<competition>\d+)/(?P<venue>\d+)/?$")
GAME_PATH_RE = re.compile(r"/game/(?P<game>\d+)/?$")
LADDER_PATH_RE = re.compile(r"/pointscore/(?P<competition>\d+)/(?P<grade>\d+)/?$")
REPORT_PATH_RE = re.compile(r"/reports/games/(?P<competition>\d+)/?$")
SCORE_RE = re.compile(r"^(?P<home>\d+)\s*-\s*(?P<away>\d+)$")
DATE_RE = re.compile(r"\b[A-Z][a-z]{2} \d{1,2} [A-Z][a-z]{2} \d{4}\b")
TIME_RE = re.compile(r"\b(\d{1,2})[:.](\d{2})\s*([AaPp][Mm])?(?!\d)")
TZID_RE = re.compile(r"^DTSTART;TZID=(?P<tzid>[^:;]+)", re.MULTILINE)
MAP_EMBED_RE = re.compile(r"!2d(?P<lng>-?\d+(?:\.\d+)?)!3d(?P<lat>-?\d+(?:\.\d+)?)")
NO_DRAWS_TEXT = "There are no draws to show"

# A round whose name says it is part of the finals series. Regular rounds are
# "Round <n>"; the site lets an organisation name any round, so this is a
# heuristic over the names seen (Semi Finals, Finals, Grand Finals, ...).
FINALS_RE = re.compile(
    r"final|semi|quarter|prelim|elimination|play-?off|knock-?out", re.IGNORECASE
)

# Badges shown beside a team in a fixture: FF "forced forfeit" and FL
# "forced loss" (a loss awarded by the organisation). Both are treated as a
# forfeit by that team, which is how the ladder counts them.
FORFEIT_BADGES = {"FF", "FL"}


class RevolutioniseURL:
    """
    A parsed revolutioniseSPORT URL.

    Recognised forms (all under ``https://www.revolutionise.com.au``)::

        /<slug>                                    the organisation
        /<slug>/games                              its draws index
        /<slug>/games/<competition>                one competition's draws
        /<slug>/games/<competition>/<grade>        one grade (reduced to the
        /<slug>/games/<competition>/<grade>/round/<n>   competition)
        /<slug>/pointscores                        the ladders index
        /<slug>/pointscore/<competition>/<grade>   one ladder
    """

    def __init__(self, url: str):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise UpstreamURLError("Not an absolute http(s) URL: %r" % url)
        host = parsed.netloc.lower()
        if host not in HOSTS:
            raise UpstreamURLError("Not a revolutionise.com.au URL: %r" % url)
        parts = [part for part in parsed.path.split("/") if part]
        if not parts or not re.match(r"^[A-Za-z0-9_-]+$", parts[0]):
            raise UpstreamURLError(
                "Expected an organisation's draws page such as "
                "%s/ccha/games, got %r" % (BASE, url)
            )
        self.slug = parts[0]
        self.competition_id: Optional[int] = None
        self.grade_id: Optional[int] = None
        rest = parts[1:]
        if not rest:
            return
        if rest[0] in ("games", "pointscore") and all(p.isdigit() for p in rest[1:3]):
            if len(rest) >= 2:
                self.competition_id = int(rest[1])
            if len(rest) >= 3:
                self.grade_id = int(rest[2])
            if len(rest) > 3 and not (
                rest[0] == "games" and rest[3] == "round" and len(rest) == 5
            ):
                raise UpstreamURLError("Not a draws URL: %r" % url)
            return
        if rest == ["pointscores"] or rest == ["games"]:
            return
        raise UpstreamURLError(
            "Expected a draws page such as %s/ccha/games or "
            "%s/ccha/games/25527, got %r" % (BASE, BASE, url)
        )

    @property
    def canonical(self) -> str:
        """The organisation's draws index."""
        return "%s/%s/games" % (BASE, self.slug)

    @property
    def season_url(self) -> str:
        """The competition's draws page, or the index when none is selected."""
        if self.competition_id is None:
            return self.canonical
        return self.competition_url(self.competition_id)

    def competition_url(self, competition_id: int) -> str:
        return "%s/%s/games/%d" % (BASE, self.slug, competition_id)

    def grade_url(self, competition_id: int, grade_id: int) -> str:
        return "%s/%s/games/%d/%d" % (BASE, self.slug, competition_id, grade_id)

    def round_url(self, competition_id: int, grade_id: int, number: int) -> str:
        return "%s/round/%d" % (self.grade_url(competition_id, grade_id), number)

    def ladder_url(self, competition_id: int, grade_id: int) -> str:
        return "%s/%s/pointscore/%d/%d" % (BASE, self.slug, competition_id, grade_id)

    def team_ical_url(self, competition_id: int, team_id: int) -> str:
        return "%s/%s/games/team/export/ical/%d/%d" % (
            BASE,
            self.slug,
            competition_id,
            team_id,
        )

    def game_url(self, game_id: int) -> str:
        return "%s/%s/game/%d" % (BASE, self.slug, game_id)


# -- parsed pages ------------------------------------------------------------


@dataclass(frozen=True)
class GradeSummary:
    """A grade as listed on the draws index."""

    competition_id: int
    competition_name: str
    grade_id: int
    grade_name: str


@dataclass(frozen=True)
class RoundSummary:
    """A round as listed on a grade page (its dates there carry no year)."""

    number: int
    name: str

    @property
    def is_final(self) -> bool:
        return bool(FINALS_RE.search(self.name))


@dataclass(frozen=True)
class GradeDetail:
    competition_name: Optional[str]
    grade_name: Optional[str]
    rounds: tuple[RoundSummary, ...]
    has_ladder: bool


@dataclass(frozen=True)
class Fixture:
    """One fixture card of a round page."""

    game_id: int
    date: Optional[date]
    time: Optional[time]
    venue_id: Optional[int]
    venue_name: Optional[str]
    field: Optional[str]
    # A finals fixture whose participants are not yet known shows "To be
    # determined" in place of a team.
    home_team_id: Optional[int]
    home_team_name: Optional[str]
    away_team_id: Optional[int]
    away_team_name: Optional[str]
    home_score: Optional[int]
    away_score: Optional[int]
    forfeiting_team_id: Optional[int]


@dataclass(frozen=True)
class Bye:
    team_id: int
    team_name: str


@dataclass(frozen=True)
class RoundDetail:
    dates: tuple[date, ...]
    fixtures: tuple[Fixture, ...]
    byes: tuple[Bye, ...]


@dataclass(frozen=True)
class LadderRow:
    team_id: int
    team_name: str
    counts: dict = field(default_factory=dict)
    points: Optional[int] = None


@dataclass(frozen=True)
class VenueDetail:
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]


# -- parsing helpers -----------------------------------------------------------


def _text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def _int(value) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_dates(text: str) -> tuple[date, ...]:
    dates = []
    for found in DATE_RE.findall(text or ""):
        try:
            dates.append(datetime.strptime(found, "%a %d %b %Y").date())
        except ValueError:
            continue
    return tuple(dates)


def _parse_time(text: str) -> Optional[time]:
    """
    Kick-off times are shown as the organisation configured them: 24-hour
    ("20:00") or 12-hour ("8:00AM", "6:00PM").
    """
    found = TIME_RE.search(text or "")
    if not found:
        return None
    hour, minute, meridiem = int(found.group(1)), int(found.group(2)), found.group(3)
    if meridiem:
        hour %= 12
        if meridiem.lower() == "pm":
            hour += 12
    try:
        return time(hour, minute)
    except ValueError:
        return None


def _path(href: Optional[str]) -> str:
    return urlparse(href or "").path


def _content_card(soup: BeautifulSoup):
    """The main content card of a draws page, or the whole document."""
    main = soup.find("main") or soup
    return main.find("div", class_="box-shadow-lg") or main


class RevolutioniseClient(HttpClient):
    """
    Scraper over the public draws pages of an organisation.

    All public methods raise :class:`UpstreamTransportError` when the
    network or HTTP layer fails, and :class:`UpstreamResponseError` when a
    page does not have the expected structure. They never return partial
    data.
    """

    def __init__(self, session: Optional[requests.Session] = None, timeout=None):
        super().__init__(session=session, timeout=timeout)

    def get_html(self, url: str) -> BeautifulSoup:
        response = self.request("GET", url, headers={"Accept": "text/html"})
        return BeautifulSoup(response.text, "html.parser")

    # -- index ---------------------------------------------------------------

    def get_index(self, url: RevolutioniseURL) -> list[GradeSummary]:
        """Every grade on the draws index, in page order, with its competition."""
        soup = self.get_html(url.canonical)
        card = _content_card(soup)
        # Competition headings carry a "Download" link naming the competition.
        names: dict[int, str] = {}
        for anchor in card.find_all("a", href=True):
            match = REPORT_PATH_RE.search(_path(anchor["href"]))
            if match:
                heading = anchor.find_previous(["h2", "h3"])
                if heading is not None:
                    names[int(match.group("competition"))] = _text(heading)
        grades = []
        seen = set()
        for anchor in card.find_all("a", href=True):
            match = GRADE_PATH_RE.search(_path(anchor["href"]))
            if not match:
                continue
            competition_id = int(match.group("competition"))
            grade_id = int(match.group("grade"))
            if (competition_id, grade_id) in seen:
                continue
            seen.add((competition_id, grade_id))
            name = _text(anchor)
            if not name:
                raise UpstreamResponseError(
                    "Grade %d/%d is listed without a name" % (competition_id, grade_id)
                )
            grades.append(
                GradeSummary(
                    competition_id=competition_id,
                    competition_name=names.get(competition_id, str(competition_id)),
                    grade_id=grade_id,
                    grade_name=name,
                )
            )
        if not grades and NO_DRAWS_TEXT not in _text(card) and not card.find("h2"):
            raise UpstreamResponseError(
                "Draws index %s did not contain a competition listing" % url.canonical
            )
        return grades

    # -- grade ---------------------------------------------------------------

    def get_grade(
        self, url: RevolutioniseURL, competition_id: int, grade_id: int
    ) -> GradeDetail:
        soup = self.get_html(url.grade_url(competition_id, grade_id))
        card = _content_card(soup)
        heading = card.find(["h2", "h1"])
        competition_name = grade_name = None
        if heading is not None:
            parts = [part.strip() for part in _text(heading).split("·")]
            if len(parts) >= 2:
                competition_name, grade_name = parts[0], parts[1]
        rounds = []
        for anchor in card.find_all("a", href=True):
            match = ROUND_PATH_RE.search(_path(anchor["href"]))
            if not match:
                continue
            rounds.append(
                RoundSummary(number=int(match.group("number")), name=_text(anchor))
            )
        has_ladder = any(
            LADDER_PATH_RE.search(_path(a["href"]))
            for a in card.find_all("a", href=True)
        )
        if not rounds and NO_DRAWS_TEXT not in _text(card):
            raise UpstreamResponseError(
                "Grade page %s did not list any rounds"
                % url.grade_url(competition_id, grade_id)
            )
        return GradeDetail(
            competition_name=competition_name,
            grade_name=grade_name,
            rounds=tuple(rounds),
            has_ladder=has_ladder,
        )

    # -- round ---------------------------------------------------------------

    def get_round(
        self, url: RevolutioniseURL, competition_id: int, grade_id: int, number: int
    ) -> RoundDetail:
        page_url = url.round_url(competition_id, grade_id, number)
        soup = self.get_html(page_url)
        card = _content_card(soup)
        heading = card.find(["h2", "h1"])
        dates: tuple[date, ...] = ()
        if heading is not None and heading.parent is not None:
            dates = _parse_dates(_text(heading.parent).replace(_text(heading), "", 1))

        fixtures = []
        for node in card.find_all("div", class_="card-hover"):
            fixtures.append(_parse_fixture(node, page_url))

        byes = []
        byes_heading = card.find(
            lambda tag: tag.name in ("h2", "h3") and _text(tag).lower() == "byes"
        )
        if byes_heading is not None:
            container = byes_heading.find_next_sibling("div") or card
            for anchor in container.find_all("a", href=True):
                match = TEAM_PATH_RE.search(_path(anchor["href"]))
                if match:
                    byes.append(
                        Bye(team_id=int(match.group("team")), team_name=_text(anchor))
                    )

        if not fixtures and not byes and NO_DRAWS_TEXT not in _text(card):
            raise UpstreamResponseError("Round page %s listed no fixtures" % page_url)
        return RoundDetail(dates=dates, fixtures=tuple(fixtures), byes=tuple(byes))

    # -- ladder --------------------------------------------------------------

    def get_ladder(
        self, url: RevolutioniseURL, competition_id: int, grade_id: int
    ) -> list[LadderRow]:
        page_url = url.ladder_url(competition_id, grade_id)
        soup = self.get_html(page_url)
        card = _content_card(soup)
        table = card.find("table")
        if table is None:
            if "no ladder" in _text(card).lower() or NO_DRAWS_TEXT in _text(card):
                return []
            raise UpstreamResponseError("Ladder page %s has no table" % page_url)
        headers = [
            re.sub(r"[^a-z]", "", _text(th).lower()) for th in table.find_all("th")
        ]
        rows = []
        body = table.find("tbody") or table
        for tr in body.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            anchor = cells[0].find("a", href=True)
            match = TEAM_PATH_RE.search(_path(anchor["href"])) if anchor else None
            if match is None:
                continue
            counts = {}
            points = None
            for header, cell in zip(headers[1:], cells[1:]):
                value = _int(_text(cell))
                if header == "points":
                    points = value
                elif header and value is not None:
                    counts[header] = value
            rows.append(
                LadderRow(
                    team_id=int(match.group("team")),
                    team_name=_text(anchor),
                    counts=counts,
                    points=points,
                )
            )
        return rows

    # -- auxiliary pages -----------------------------------------------------

    def get_timezone(
        self, url: RevolutioniseURL, competition_id: int, team_id: int
    ) -> Optional[str]:
        """
        The IANA time zone of a competition, from the ``TZID`` of a team's
        iCalendar export. ``None`` when the feed has no timed events.
        """
        response = self.request(
            "GET",
            url.team_ical_url(competition_id, team_id),
            headers={"Accept": "text/calendar, text/plain"},
        )
        match = TZID_RE.search(response.text)
        if not match:
            return None
        tzid = match.group("tzid").strip()
        try:
            ZoneInfo(tzid)
        except (ZoneInfoNotFoundError, ValueError):
            raise UpstreamResponseError("Unknown time zone %r in iCalendar" % tzid)
        return tzid

    def get_venue_detail(self, url: RevolutioniseURL, game_id: int) -> VenueDetail:
        """The venue's address and map coordinates from a fixture's page."""
        soup = self.get_html(url.game_url(game_id))
        address = None
        label = soup.find(
            lambda tag: tag.name == "div"
            and _text(tag) == "Venue"
            and "text-muted" in (tag.get("class") or [])
        )
        if label is not None and label.parent is not None:
            detail = label.parent.find("div", class_="font-size-sm", recursive=False)
            siblings = [
                d
                for d in label.parent.find_all("div", recursive=False)
                if d is not label
            ]
            if siblings:
                address = _text(siblings[-1]) or None
            elif detail is not None:
                address = _text(detail) or None
        latitude = longitude = None
        for iframe in soup.find_all("iframe", src=True):
            match = MAP_EMBED_RE.search(iframe["src"])
            if match:
                latitude = float(match.group("lat"))
                longitude = float(match.group("lng"))
                break
        return VenueDetail(address=address, latitude=latitude, longitude=longitude)


def _parse_fixture(node, page_url: str) -> Fixture:
    anchors = node.find_all("a", href=True)
    game_id = None
    for anchor in anchors:
        match = GAME_PATH_RE.search(_path(anchor["href"]))
        if match:
            game_id = int(match.group("game"))
            break
    if game_id is None:
        raise UpstreamResponseError("A fixture on %s has no game link" % page_url)

    venue_id = venue_name = field_name = None
    for anchor in anchors:
        match = VENUE_PATH_RE.search(_path(anchor["href"]))
        if match:
            venue_id = int(match.group("venue"))
            venue_name = _text(anchor) or None
            sibling = anchor.find_next_sibling("div")
            field_name = _text(sibling) or None if sibling is not None else None
            break

    # Teams, the score between them and any forfeit badge, in document order
    # within the column that holds them; a badge belongs to the team whose
    # name precedes it. A participant yet to be determined (a final before
    # the regular season is complete) is a muted span rather than a link.
    teams = []
    forfeiting = None
    score_text = None
    team_anchors = [a for a in anchors if TEAM_PATH_RE.search(_path(a["href"]))]
    if team_anchors:
        column = team_anchors[0].parent
    else:
        placeholder = node.find("span", class_="text-muted")
        column = placeholder.parent if placeholder is not None else None
    if column is None:
        raise UpstreamResponseError(
            "Fixture %d on %s does not name its teams" % (game_id, page_url)
        )
    for child in column.children:
        name = getattr(child, "name", None)
        classes = child.get("class") or [] if name else []
        if name == "a" and child in team_anchors:
            match = TEAM_PATH_RE.search(_path(child["href"]))
            teams.append((int(match.group("team")), _text(child)))
        elif name == "span" and "badge" in classes:
            if _text(child).upper() in FORFEIT_BADGES and teams and teams[-1][0]:
                forfeiting = teams[-1][0]
        elif name == "span" and "text-muted" in classes:
            teams.append((None, None))
        elif name == "div" and len(teams) == 1:
            badge = child.find("span", class_="badge")
            if badge is not None:
                if _text(badge).upper() in FORFEIT_BADGES and teams[-1][0]:
                    forfeiting = teams[-1][0]
            else:
                score_text = _text(child)
    if len(teams) != 2:
        raise UpstreamResponseError(
            "Fixture %d on %s does not name two teams" % (game_id, page_url)
        )
    (home_id, home_name), (away_id, away_name) = teams
    home_score = away_score = None
    if score_text:
        match = SCORE_RE.match(score_text)
        if match:
            home_score, away_score = int(match.group("home")), int(match.group("away"))

    # The date/time column is the first text block of the card.
    when = node.find("div", class_="col-md")
    when_text = _text(when) if when is not None else ""
    dates = _parse_dates(when_text)
    return Fixture(
        game_id=game_id,
        date=dates[0] if dates else None,
        time=_parse_time(when_text),
        venue_id=venue_id,
        venue_name=venue_name,
        field=field_name,
        home_team_id=home_id,
        home_team_name=home_name,
        away_team_id=away_id,
        away_team_name=away_name,
        home_score=home_score,
        away_score=away_score,
        forfeiting_team_id=forfeiting,
    )


# -- points inference ------------------------------------------------------------

# Points per outcome are searched over these ranges; anything outside them is
# not something a ladder on this platform has been seen to use.
POINT_RANGES = {
    "wins": range(0, 7),
    "draws": range(0, 5),
    "losses": range(0, 4),
    # A loss by forfeit may be penalised (QUT Netball deducts a point).
    "forfeits": range(-3, 4),
    "byes": range(0, 7),
}
DEFAULT_DRAW_POINTS = 1


def infer_ladder_template(
    rows: list[LadderRow],
) -> tuple[Optional[RemoteLadderTemplate], list[str]]:
    """
    Work out the points scheme behind a ladder from its totals.

    revolutioniseSPORT does not publish the points awarded for a win, draw or
    loss, only each team's totals (and, for some sports, bonus points, which
    are added as they stand). With a few results in, the scheme is the
    unique small-integer solution of ``wins*W + draws*D + ... = points`` over
    the rows. Returns the template and any assumptions made, or ``None``
    when nothing has been played yet or the totals admit more than one
    scheme (in which case the caller falls back to defaults).
    """
    rows = [row for row in rows if row.points is not None]
    active = [
        name for name in POINT_RANGES if any(row.counts.get(name, 0) for row in rows)
    ]
    if not rows or not active:
        return None, []
    solutions = []
    for combo in itertools.product(*(POINT_RANGES[name] for name in active)):
        if all(
            sum(points * row.counts.get(name, 0) for points, name in zip(combo, active))
            # A "Bonus" column, where the ladder has one, is added as it
            # stands (it can be negative: a penalty).
            + row.counts.get("bonus", 0) == row.points
            for row in rows
        ):
            solutions.append(combo)
            if len(solutions) > 1:
                break
    if len(solutions) != 1:
        return None, []
    values = dict(zip(active, solutions[0]))
    notes = []
    if "wins" not in values:
        return None, []
    if "draws" not in values:
        values["draws"] = DEFAULT_DRAW_POINTS
        notes.append(
            "no draws yet; %d point(s) assumed for a draw" % DEFAULT_DRAW_POINTS
        )
    template = RemoteLadderTemplate(
        name="Inferred from the revolutioniseSPORT ladder",
        points_win=values["wins"],
        points_draw=values["draws"],
        points_loss=values.get("losses", 0),
        points_bye=values.get("byes", 0),
        # A win by forfeit is counted as a win on the platform's ladder.
        points_forfeit_for=values["wins"],
        points_forfeit_against=values.get("forfeits", 0),
        forfeit_counts_as_played=True,
    )
    return template, notes


# -- backend -----------------------------------------------------------------


class RevolutioniseBackend(BaseUpstreamBackend):
    key = "revolutionise"
    name = "revolutioniseSPORT"
    competition_url_example = "https://www.revolutionise.com.au/ccha/games"
    season_url_example = "https://www.revolutionise.com.au/ccha/games/25527"

    def matches(self, url: str) -> bool:
        return urlparse(url).netloc.lower() in HOSTS

    def parse_competition_url(self, url: str) -> str:
        return RevolutioniseURL(url).canonical

    def parse_season_url(self, url: str, competition_url: str) -> str:
        parsed = RevolutioniseURL(url)
        organisation = RevolutioniseURL(competition_url)
        if parsed.slug != organisation.slug:
            raise UpstreamURLError(
                "Enter a draws page of %s, for example %s"
                % (organisation.canonical, organisation.canonical + "/25527")
            )
        return parsed.season_url

    def new_client(self, session: Optional[requests.Session] = None):
        return RevolutioniseClient(session=session)

    def fetch_snapshot(self, season, client=None) -> list[RemoteCompetition]:
        if client is None:
            client = self.new_client()
        url = RevolutioniseURL(season.upstream_url)
        grades = client.get_index(url)
        if url.competition_id is not None:
            grades = [g for g in grades if g.competition_id == url.competition_id]
            if not grades:
                raise UpstreamResponseError(
                    "Competition %d is not listed on %s"
                    % (url.competition_id, url.canonical)
                )
        # The same grade name can appear in two competitions synchronised
        # into one season; qualify such names with the competition.
        name_counts = Counter(grade.grade_name for grade in grades)
        fallback_tz = str(season.timezone) if season.timezone else None
        builder = _SnapshotBuilder(client, url, fallback_tz)
        snapshots = []
        for grade in grades:
            name = grade.grade_name
            if name_counts[name] > 1:
                name = "%s (%s)" % (grade.grade_name, grade.competition_name)
            snapshots.append(builder.build(grade, name))
        return snapshots


class _SnapshotBuilder:
    """Assembles a :class:`RemoteCompetition` per grade, caching what is shared."""

    def __init__(self, client: RevolutioniseClient, url: RevolutioniseURL, fallback_tz):
        self.client = client
        self.url = url
        self.fallback_tz = fallback_tz
        self._timezones: dict[int, Optional[str]] = {}
        self._venues: dict[int, VenueDetail] = {}

    def build(self, grade: GradeSummary, name: str) -> RemoteCompetition:
        detail = self.client.get_grade(self.url, grade.competition_id, grade.grade_id)
        rounds = [
            (
                summary,
                self.client.get_round(
                    self.url, grade.competition_id, grade.grade_id, summary.number
                ),
            )
            for summary in detail.rounds
        ]
        ladder = (
            self.client.get_ladder(self.url, grade.competition_id, grade.grade_id)
            if detail.has_ladder
            else []
        )

        # Teams: ladder order first (it includes teams yet to play), then
        # anything a fixture or bye names that the ladder does not.
        teams: dict[int, str] = {row.team_id: row.team_name for row in ladder}
        for _, round_detail in rounds:
            for fixture in round_detail.fixtures:
                if fixture.home_team_id is not None:
                    teams.setdefault(fixture.home_team_id, fixture.home_team_name)
                if fixture.away_team_id is not None:
                    teams.setdefault(fixture.away_team_id, fixture.away_team_name)
            for bye in round_detail.byes:
                teams.setdefault(bye.team_id, bye.team_name)

        tzname = self._timezone(grade.competition_id, next(iter(teams), None))
        tzinfo = ZoneInfo(tzname) if tzname else None
        today = datetime.now(tzinfo).date() if tzinfo else date.today()

        matches = []
        forfeit_scores = Counter()
        for summary, round_detail in rounds:
            round_type = ROUND_FINAL if summary.is_final else ROUND_REGULAR
            for fixture in round_detail.fixtures:
                venue = self._venue(fixture, tzname)
                status = STATUS_PRE_GAME
                if fixture.forfeiting_team_id is not None:
                    status = STATUS_FORFEIT
                    winner_score = (
                        fixture.away_score
                        if fixture.forfeiting_team_id == fixture.home_team_id
                        else fixture.home_score
                    )
                    if winner_score:
                        forfeit_scores[winner_score] += 1
                elif fixture.home_score is not None and fixture.away_score is not None:
                    status = STATUS_FINAL
                matches.append(
                    RemoteMatch(
                        id=fixture.game_id,
                        round_number=summary.number,
                        round_type=round_type,
                        round_name=summary.name,
                        start=_combine(fixture.date, fixture.time, tzinfo),
                        has_time=fixture.time is not None,
                        status=status,
                        home_team_id=fixture.home_team_id,
                        away_team_id=fixture.away_team_id,
                        is_tba=(
                            fixture.home_team_id is None or fixture.away_team_id is None
                        ),
                        home_score=fixture.home_score,
                        away_score=fixture.away_score,
                        forfeiting_team_id=fixture.forfeiting_team_id,
                        venue=venue,
                        field=fixture.field,
                    )
                )
            # A bye has no page of its own; its date is the round's and it
            # counts once the round is over.
            bye_date = max(round_detail.dates) if round_detail.dates else None
            for bye in round_detail.byes:
                matches.append(
                    RemoteMatch(
                        id="bye/%d/%d/%d"
                        % (grade.grade_id, summary.number, bye.team_id),
                        round_number=summary.number,
                        round_type=round_type,
                        round_name=summary.name,
                        start=_combine(bye_date, None, tzinfo),
                        has_time=False,
                        status=(
                            STATUS_FINAL
                            if bye_date is not None and bye_date < today
                            else STATUS_PRE_GAME
                        ),
                        home_team_id=bye.team_id,
                        is_bye=True,
                    )
                )

        warnings = []
        template, notes = infer_ladder_template(ladder)
        if template is None:
            warnings.append(
                "the points scheme could not be inferred from the ladder yet, so "
                "the default points formula was applied; check the division's "
                "ladder settings"
                if ladder
                else "the grade has no ladder, so the default points formula was applied"
            )
        else:
            warnings.extend(notes)
            if forfeit_scores:
                template = template.model_copy(
                    update={"forfeit_score": forfeit_scores.most_common(1)[0][0]}
                )

        return RemoteCompetition(
            id="%d/%d" % (grade.competition_id, grade.grade_id),
            name=name,
            teams=tuple(RemoteTeam(id=tid, name=tname) for tid, tname in teams.items()),
            matches=tuple(matches),
            ladder_template=template,
            warnings=tuple(warnings),
        )

    def _timezone(self, competition_id: int, team_id: Optional[int]) -> Optional[str]:
        if competition_id not in self._timezones:
            tzname = None
            if team_id is not None:
                # Auxiliary: a time zone can still be taken from the season,
                # so neither a bad feed nor an unreachable one aborts the sync.
                try:
                    tzname = self.client.get_timezone(self.url, competition_id, team_id)
                except UpstreamError as exc:
                    logger.warning(
                        "Time zone of revolutioniseSPORT competition %d unavailable: %s",
                        competition_id,
                        exc,
                    )
            self._timezones[competition_id] = tzname or self.fallback_tz
        return self._timezones[competition_id]

    def _venue(self, fixture: Fixture, tzname: Optional[str]) -> Optional[RemoteVenue]:
        if fixture.venue_id is None or not fixture.venue_name:
            return None
        detail = self._venues.get(fixture.venue_id)
        if detail is None:
            # Auxiliary: coordinates only decorate a newly created venue.
            try:
                detail = self.client.get_venue_detail(self.url, fixture.game_id)
            except UpstreamError as exc:
                logger.warning(
                    "Details of revolutioniseSPORT venue %d unavailable: %s",
                    fixture.venue_id,
                    exc,
                )
                detail = VenueDetail(None, None, None)
            self._venues[fixture.venue_id] = detail
        return RemoteVenue(
            id=fixture.venue_id,
            name=fixture.venue_name,
            timezone=tzname,
            latitude=detail.latitude,
            longitude=detail.longitude,
        )


def _combine(day: Optional[date], at: Optional[time], tzinfo) -> Optional[datetime]:
    if day is None:
        return None
    return datetime.combine(day, at or time(0, 0), tzinfo=tzinfo or ZoneInfo("UTC"))
