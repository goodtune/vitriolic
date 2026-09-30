"""
Model Context Protocol (MCP) tools for the competition management system.

The tools in this module are what an AI agent uses to answer the kinds of
questions people ask about a competition: "when is my next game?", "what
time are Australia playing New Zealand?", "who is top of the pool?" or "how
many Men's games are being live streamed at the Euros?".

They are deliberately *not* a generic query layer over the models. Each tool
answers a human-shaped question, returns compact JSON that an agent can
reason over, and the narrowing tools (``upcoming_events``, ``recent_events``
and ``search``) give the agent the identifiers it needs for the detail tools
without having to guess.

Hosting
-------
``build_server`` turns the toolset into an ``mcp.server.mcpserver.MCPServer``
(the official MCP Python SDK, 2.x): each public method of
``CompetitionToolset`` becomes a tool named after the method and described
by its docstring, with its input schema derived from the type hints. The
Django request that carried the MCP call is made available to the toolset
through a context variable that ``views.MCPView`` sets, so ``whoami`` can
identify the caller and superusers can see draft divisions.

Visibility
----------
The tools follow the same rules as the public web site: only enabled
competitions and seasons are visible, and divisions marked as draft are
hidden unless the calling user is a superuser.

Deployment
----------
Route ``tournamentcontrol.competition.mcp.urls`` and, optionally, set
``TOURNAMENTCONTROL_MCP_NAME`` and ``TOURNAMENTCONTROL_MCP_INSTRUCTIONS``.
See ``docs/mcp.md``.
"""

import contextvars
import datetime
import functools
import inspect
from typing import Any, Literal

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, F, Max, Min, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.html import strip_tags
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from tournamentcontrol.competition.constants import ClubStatus
from tournamentcontrol.competition.models import (
    Club,
    Competition,
    Division,
    Match,
    Person,
    Season,
    Stage,
    Team,
    Venue,
)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_DAYS = 366

#: The Django request carrying the MCP call currently being served, set by
#: ``views.MCPView`` for the duration of the request.
current_request = contextvars.ContextVar("tournamentcontrol_mcp_request")

MatchStatus = Literal["any", "upcoming", "past", "completed"]
MatchGroupBy = Literal[
    "competition",
    "season",
    "division",
    "stage",
    "pool",
    "date",
    "venue",
    "live_stream",
    "status",
]

INSTRUCTIONS = """
Competition management tools
============================

Data is organised as Competition > Season > Division > Stage > Pool > Match.
A *season* is one edition of a competition (for example the 2026 edition of
the European Championships); people call this the "event" or "tournament".
Teams belong to a division within a season and to a club. In international
competitions the club is the nation, so "Australia" is a club with a team in
each division it enters (Men's Open, Women's Open, Mixed Open, ...).

Recommended approach:

1. Narrow the surface area first. `upcoming_events` and `recent_events` tell
   you which seasons are on now, soon, or just finished. `search` finds a
   competition, season, division, team, club or venue by name and returns
   the identifiers the other tools need. `get_season` describes the
   divisions, stages, pools and venues of one season.
2. Answer with the detail tools: `list_matches` (schedules and results,
   filter by team, club, opponent, division, venue, date range or status),
   `count_matches` (aggregate questions such as "how many games are being
   live streamed per division"), `get_ladder` (standings), `get_team` (next
   and last match plus ladder position) and `get_match`.
3. For "my" questions ("when is my next game?") call `whoami` first; it
   identifies the connected user's teams and their next match. If the
   caller is anonymous, ask which team or club they follow and use `search`.

Times are given in the local time of the venue (falling back to the season)
as ISO 8601 strings with a UTC offset, alongside the time zone name. Dates
are ISO 8601 (YYYY-MM-DD). Identifiers are stable integers; slugs are also
returned so links to the public web site can be constructed.
""".strip()


def _clamp(value, default, maximum, minimum=1):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def _ref(obj):
    """Compact reference to a node: identifier, title and slug when it has one."""
    if obj is None:
        return None
    res = {"id": obj.pk, "title": obj.title}
    slug = getattr(obj, "slug", None)
    if slug:
        res["slug"] = slug
    return res


def _tzname(tzinfo):
    return str(tzinfo) if tzinfo else None


def _place(place, detail=False):
    """
    Describe where a match is played. A match is scheduled at a ``Place``
    which is either a ``Venue`` or one of its ``Ground`` sub-locations.
    """
    if place is None:
        return {"venue": None, "ground": None}
    try:
        venue = place.ground.venue
        ground = place
    except ObjectDoesNotExist:
        venue = place
        ground = None
    res = {
        "venue": {"id": venue.pk, "title": venue.title},
        "ground": {"id": ground.pk, "title": ground.title} if ground else None,
    }
    if detail:
        res["timezone"] = _tzname(place.timezone)
        res["latitude"] = float(place.latitude) if place.latitude else None
        res["longitude"] = float(place.longitude) if place.longitude else None
    return res


def _team_ref(team):
    if team is None:
        return None
    return {
        "id": team.pk,
        "title": team.title,
        "slug": team.slug,
        "club": _ref(team.club),
    }


def _match_team(match, field):
    """
    The home or away team of a match. Teams that are yet to be decided (for
    example "Winner Semi Final 1" or "1st Pool A") have no identifier, only a
    descriptive title.
    """
    team = getattr(match, field)
    if team is not None:
        return _team_ref(team)
    title = getattr(match, f"{field}_title", None)
    if title is None:
        title = getattr(match, f"get_{field}_plain")()
    title = strip_tags(str(title or "")).strip() or None
    return {"id": None, "title": title, "slug": None, "club": None}


def _match_tzinfo(match):
    if match.play_at is not None and match.play_at.timezone:
        return match.play_at.timezone
    return match.stage.division.season.timezone


def _match_status(match, now, today):
    if match.is_bye:
        return "bye"
    if match.is_washout:
        return "washout"
    if match.is_forfeit:
        return "forfeit"
    if match.home_team_score is not None and match.away_team_score is not None:
        return "completed"
    if match.datetime is not None:
        return "upcoming" if match.datetime >= now else "awaiting_result"
    if match.date is not None:
        return "upcoming" if match.date >= today else "awaiting_result"
    return "unscheduled"


def _match_summary(match, now, today):
    season = match.stage.division.season
    tzinfo = _match_tzinfo(match)
    kick_off = None
    if match.datetime is not None:
        kick_off = timezone.localtime(match.datetime, tzinfo).isoformat()

    winner = match.winner
    status = _match_status(match, now, today)
    is_draw = (
        status == "completed"
        and not match.is_forfeit
        and match.home_team_score == match.away_team_score
    )

    live_stream_url = None
    if match.live_stream and match.external_identifier:
        live_stream_url = f"https://youtu.be/{match.external_identifier}"

    res = {
        "id": match.pk,
        "uuid": str(match.uuid),
        "competition": _ref(season.competition),
        "season": _ref(season),
        "division": _ref(match.stage.division),
        "stage": _ref(match.stage),
        "pool": _ref(match.stage_group),
        "round": match.round,
        "label": match.label or None,
        "datetime": kick_off,
        "date": match.date.isoformat() if match.date else None,
        "time": match.time.strftime("%H:%M") if match.time else None,
        "timezone": _tzname(tzinfo),
        "home_team": _match_team(match, "home_team"),
        "away_team": _match_team(match, "away_team"),
        "home_team_score": match.home_team_score,
        "away_team_score": match.away_team_score,
        "status": status,
        "winner": _team_ref(winner) if winner else None,
        "is_draw": is_draw,
        "live_stream": match.live_stream,
        "live_stream_url": live_stream_url,
        "videos": list(match.videos or []),
    }
    res.update(_place(match.play_at))
    return res


def _ladder_entry(position, entry):
    return {
        "position": position,
        "team": _team_ref(entry.team),
        "played": entry.played,
        "win": entry.win,
        "loss": entry.loss,
        "draw": entry.draw,
        "bye": entry.bye,
        "forfeit_for": entry.forfeit_for,
        "forfeit_against": entry.forfeit_against,
        "score_for": entry.score_for,
        "score_against": entry.score_against,
        "difference": float(entry.difference),
        "percentage": float(entry.percentage) if entry.percentage is not None else None,
        "bonus_points": entry.bonus_points,
        "points": float(entry.points),
    }


def _words_query(query, fields):
    """
    Every whitespace separated word of ``query`` must match at least one of
    the ``fields`` (case-insensitive substring match).
    """
    q = Q()
    for word in query.split():
        word_q = Q()
        for field in fields:
            word_q |= Q(**{f"{field}__icontains": word})
        q &= word_q
    return q


class CompetitionToolset:
    """
    Schedule and results tools for the competition management system.

    Every public method is published as an MCP tool by ``build_server``.
    ``request`` is the Django request that carried the MCP call (or ``None``
    when called outside one); its ``user`` decides what is visible.
    """

    def __init__(self, request=None):
        self.request = request

    # -- helpers ---------------------------------------------------------

    def _user(self):
        return getattr(self.request, "user", None)

    def _is_superuser(self):
        return bool(getattr(self._user(), "is_superuser", False))

    def _now(self):
        now = timezone.now()
        return now, timezone.localdate(now)

    def _visible_seasons(self):
        return Season.objects.filter(
            enabled=True, competition__enabled=True
        ).select_related("competition")

    def _visible_divisions(self):
        divisions = Division.objects.filter(
            season__enabled=True, season__competition__enabled=True
        )
        if not self._is_superuser():
            divisions = divisions.public()
        return divisions.select_related("season__competition")

    def _visible_teams(self):
        teams = Team.objects.filter(
            division__season__enabled=True,
            division__season__competition__enabled=True,
        )
        if not self._is_superuser():
            teams = teams.filter(division__draft=False)
        return teams.select_related("club", "division__season__competition")

    def _visible_stages(self):
        stages = Stage.objects.filter(
            division__season__enabled=True,
            division__season__competition__enabled=True,
        )
        if not self._is_superuser():
            stages = stages.filter(division__draft=False)
        return stages.select_related("division__season__competition")

    def _visible_matches(self, annotated=True):
        """
        Matches the calling user is allowed to see.

        ``Match.objects`` annotates placeholder titles for undecided teams
        which is exactly what we want when listing matches, but those
        annotations get in the way of ``values().annotate()`` aggregation,
        so counting uses the plain base manager instead.
        """
        manager = Match.objects if annotated else Match._base_manager
        matches = manager.filter(
            stage__division__season__enabled=True,
            stage__division__season__competition__enabled=True,
        )
        if not self._is_superuser():
            matches = matches.exclude(stage__division__draft=True)
        return matches

    def _detailed(self, matches):
        return matches.select_related(
            "stage__division__season__competition",
            "stage_group",
            "play_at__ground__venue",
            "home_team__club",
            "away_team__club",
            "forfeit_winner",
        ).defer("live_stream_thumbnail_image")

    def _team_matches(self, team):
        return self._detailed(
            self._visible_matches().filter(Q(home_team=team) | Q(away_team=team))
        ).playable()

    def _next_match(self, team, now, today):
        match = (
            self._team_matches(team)
            .filter(Q(datetime__gte=now) | Q(datetime__isnull=True, date__gte=today))
            .order_by(F("datetime").asc(nulls_last=True), "date", "time", "pk")
            .first()
        )
        return _match_summary(match, now, today) if match else None

    def _last_match(self, team, now, today):
        match = (
            self._team_matches(team)
            .filter(Q(datetime__lt=now) | Q(datetime__isnull=True, date__lt=today))
            .order_by(F("datetime").desc(nulls_last=True), "-date", "-time", "-pk")
            .first()
        )
        return _match_summary(match, now, today) if match else None

    def _filter_matches(
        self,
        matches,
        *,
        competition_id=None,
        season_id=None,
        division_id=None,
        stage_id=None,
        team_id=None,
        club_id=None,
        opponent_team_id=None,
        opponent_club_id=None,
        venue_id=None,
        date_from=None,
        date_to=None,
        status="any",
        live_stream_only=False,
        include_byes=True,
    ):
        if competition_id is not None:
            matches = matches.filter(
                stage__division__season__competition_id=competition_id
            )
        if season_id is not None:
            matches = matches.filter(stage__division__season_id=season_id)
        if division_id is not None:
            matches = matches.filter(stage__division_id=division_id)
        if stage_id is not None:
            matches = matches.filter(stage_id=stage_id)
        if venue_id is not None:
            matches = matches.filter(
                Q(play_at_id=venue_id) | Q(play_at__ground__venue_id=venue_id)
            )

        # A team (or every team of a club) can be on either side of a
        # match, and so can the opponent, so build both orientations.
        subject_home, subject_away = Q(), Q()
        if team_id is not None:
            subject_home &= Q(home_team_id=team_id)
            subject_away &= Q(away_team_id=team_id)
        if club_id is not None:
            subject_home &= Q(home_team__club_id=club_id)
            subject_away &= Q(away_team__club_id=club_id)
        opponent_home, opponent_away = Q(), Q()
        if opponent_team_id is not None:
            opponent_home &= Q(home_team_id=opponent_team_id)
            opponent_away &= Q(away_team_id=opponent_team_id)
        if opponent_club_id is not None:
            opponent_home &= Q(home_team__club_id=opponent_club_id)
            opponent_away &= Q(away_team__club_id=opponent_club_id)

        if subject_home and opponent_home:
            matches = matches.filter(
                (subject_home & opponent_away) | (subject_away & opponent_home)
            )
        elif subject_home:
            matches = matches.filter(subject_home | subject_away)
        elif opponent_home:
            matches = matches.filter(opponent_home | opponent_away)

        if date_from is not None:
            matches = matches.filter(date__gte=date_from)
        if date_to is not None:
            matches = matches.filter(date__lte=date_to)

        now, today = self._now()
        if status == "upcoming":
            matches = matches.filter(
                Q(datetime__gte=now) | Q(datetime__isnull=True, date__gte=today)
            )
        elif status == "past":
            matches = matches.filter(
                Q(datetime__lt=now) | Q(datetime__isnull=True, date__lt=today)
            )
        elif status == "completed":
            matches = matches.filter(
                home_team_score__isnull=False, away_team_score__isnull=False
            )

        if live_stream_only:
            matches = matches.filter(live_stream=True)
        if not include_byes:
            matches = matches.playable()

        return matches

    def _seasons_with_dates(self):
        match_q = Q(divisions__stages__matches__date__isnull=False)
        division_q = None
        if not self._is_superuser():
            match_q &= Q(divisions__draft=False)
            division_q = Q(divisions__draft=False)
        return self._visible_seasons().annotate(
            first_date=Min("divisions__stages__matches__date", filter=match_q),
            last_date=Max("divisions__stages__matches__date", filter=match_q),
            division_count=Count("divisions", filter=division_q, distinct=True),
            match_count=Count(
                "divisions__stages__matches", filter=match_q, distinct=True
            ),
        )

    def _event(self, season, today):
        if season.first_date is None:
            status = "unscheduled"
        elif season.first_date > today:
            status = "upcoming"
        elif season.last_date < today:
            status = "finished"
        else:
            status = "in_progress"
        return {
            "season": _ref(season),
            "competition": _ref(season.competition),
            "title": f"{season.competition.title} {season.title}",
            "status": status,
            "first_match_date": (
                season.first_date.isoformat() if season.first_date else None
            ),
            "last_match_date": (
                season.last_date.isoformat() if season.last_date else None
            ),
            "days_until_start": (
                (season.first_date - today).days if season.first_date else None
            ),
            "hashtag": season.hashtag or None,
            "timezone": _tzname(season.timezone),
            "live_stream": season.live_stream,
            "division_count": season.division_count,
            "match_count": season.match_count,
        }

    def _get_season(self, season_id):
        return self._visible_seasons().filter(pk=season_id).first()

    def _get_team(self, team_id):
        return self._visible_teams().filter(pk=team_id).first()

    # -- narrowing tools -------------------------------------------------

    def upcoming_events(self, days: int = 30, limit: int = 20) -> dict[str, Any]:
        """
        Seasons (events, tournaments) that are in progress now or have their
        first match within the next ``days`` days, soonest first.

        Call this first when a question refers to an event by a nickname
        ("the Euros", "the World Cup", "this weekend") or gives no event at
        all, then use the returned season and competition identifiers with
        the other tools. Each entry reports whether the event is "upcoming"
        or "in_progress", its first and last match dates, hashtag, time zone
        and whether it is live streamed.
        """
        days = _clamp(days, 30, MAX_DAYS, minimum=0)
        limit = _clamp(limit, 20, MAX_LIMIT)
        __, today = self._now()
        seasons = (
            self._seasons_with_dates()
            .filter(
                last_date__gte=today,
                first_date__lte=today + datetime.timedelta(days=days),
            )
            .order_by("first_date", "competition__order", "order")
        )
        return {
            "today": today.isoformat(),
            "days": days,
            "events": [self._event(season, today) for season in seasons[:limit]],
        }

    def recent_events(self, days: int = 30, limit: int = 20) -> dict[str, Any]:
        """
        Seasons (events, tournaments) that had matches in the last ``days``
        days, most recently active first. Events still in progress are
        included and flagged "in_progress".

        Use this for questions about results ("how did we go at the
        Nationals?", "who won last weekend?") to find the season identifier.
        """
        days = _clamp(days, 30, MAX_DAYS, minimum=0)
        limit = _clamp(limit, 20, MAX_LIMIT)
        __, today = self._now()
        seasons = (
            self._seasons_with_dates()
            .filter(
                first_date__lte=today,
                last_date__gte=today - datetime.timedelta(days=days),
            )
            .order_by("-last_date", "competition__order", "order")
        )
        return {
            "today": today.isoformat(),
            "days": days,
            "events": [self._event(season, today) for season in seasons[:limit]],
        }

    def search(self, query: str, limit: int = 10) -> dict[str, Any]:
        """
        Find competitions, seasons, divisions, teams, clubs and venues whose
        names contain every word of ``query`` (case-insensitive), returning
        up to ``limit`` of each with the identifiers the other tools need.

        Team results include the club, division, season and competition so
        "Australia" resolves to one team per division it has entered, most
        recent season first. A season is matched on its own title, its
        hashtag and its competition's title, so "European Championships
        2026" or "Euros2026" both work. Use ``upcoming_events`` instead when
        the event is only referred to by a nickname.
        """
        query = (query or "").strip()
        limit = _clamp(limit, 10, MAX_LIMIT)
        if not query:
            return {"error": "Provide one or more words to search for."}

        competitions = Competition.objects.filter(enabled=True).filter(
            _words_query(query, ["title", "short_title", "slug"])
        )
        seasons = self._visible_seasons().filter(
            _words_query(
                query,
                [
                    "title",
                    "short_title",
                    "hashtag",
                    "competition__title",
                    "competition__short_title",
                ],
            )
        )
        divisions = self._visible_divisions().filter(
            _words_query(
                query,
                [
                    "title",
                    "short_title",
                    "season__title",
                    "season__competition__title",
                ],
            )
        )
        teams = self._visible_teams().filter(
            _words_query(
                query,
                [
                    "title",
                    "club__title",
                    "division__title",
                    "division__season__title",
                    "division__season__competition__title",
                ],
            )
        )
        clubs = Club.objects.exclude(status=ClubStatus.HIDDEN).filter(
            _words_query(query, ["title", "short_title", "abbreviation"])
        )
        venues = (
            Venue.objects.filter(
                season__enabled=True, season__competition__enabled=True
            )
            .select_related("season__competition")
            .filter(_words_query(query, ["title", "abbreviation"]))
        )

        return {
            "query": query,
            "competitions": [_ref(c) for c in competitions[:limit]],
            "seasons": [
                {
                    "season": _ref(s),
                    "competition": _ref(s.competition),
                    "title": f"{s.competition.title} {s.title}",
                    "hashtag": s.hashtag or None,
                }
                for s in seasons[:limit]
            ],
            "divisions": [
                {
                    "division": _ref(d),
                    "season": _ref(d.season),
                    "competition": _ref(d.season.competition),
                }
                for d in divisions[:limit]
            ],
            "teams": [
                {
                    "team": _team_ref(t),
                    "division": _ref(t.division),
                    "season": _ref(t.division.season),
                    "competition": _ref(t.division.season.competition),
                }
                for t in teams[:limit]
            ],
            "clubs": [
                {
                    "club": _ref(c),
                    "abbreviation": c.abbreviation or None,
                }
                for c in clubs[:limit]
            ],
            "venues": [
                {
                    "venue": {"id": v.pk, "title": v.title},
                    "season": _ref(v.season),
                    "competition": _ref(v.season.competition),
                    "timezone": _tzname(v.timezone),
                }
                for v in venues[:limit]
            ],
        }

    # -- structure tools -------------------------------------------------

    def get_season(self, season_id: int) -> dict[str, Any]:
        """
        Describe one season (event): its divisions with their stages and
        pools, the venues and grounds it is played at, the span of match
        dates, and how many matches are scheduled, completed, still to come
        and live streamed.

        Use the division, stage, pool and venue identifiers it returns to
        filter ``list_matches``, ``count_matches`` and ``get_ladder``.
        """
        season = self._get_season(season_id)
        if season is None:
            return {"error": f"Season {season_id} was not found."}

        now, today = self._now()
        divisions = (
            self._visible_divisions()
            .filter(season=season)
            .annotate(team_count=Count("teams", distinct=True))
            .prefetch_related("stages__pools")
            .order_by("order")
        )
        matches = self._visible_matches(annotated=False).filter(
            stage__division__season=season
        )
        summary = matches.aggregate(
            total=Count("id"),
            completed=Count(
                "id",
                filter=Q(home_team_score__isnull=False, away_team_score__isnull=False),
            ),
            upcoming=Count(
                "id",
                filter=(
                    Q(datetime__gte=now) | Q(datetime__isnull=True, date__gte=today)
                ),
            ),
            live_streamed=Count("id", filter=Q(live_stream=True)),
            first_date=Min("date"),
            last_date=Max("date"),
        )

        return {
            "season": _ref(season),
            "competition": _ref(season.competition),
            "title": f"{season.competition.title} {season.title}",
            "hashtag": season.hashtag or None,
            "timezone": _tzname(season.timezone),
            "start_date": season.start_date.isoformat() if season.start_date else None,
            "first_match_date": (
                summary["first_date"].isoformat() if summary["first_date"] else None
            ),
            "last_match_date": (
                summary["last_date"].isoformat() if summary["last_date"] else None
            ),
            "complete": season.complete,
            "live_stream": season.live_stream,
            "matches": {
                "total": summary["total"],
                "completed": summary["completed"],
                "upcoming": summary["upcoming"],
                "live_streamed": summary["live_streamed"],
            },
            "divisions": [
                {
                    "id": division.pk,
                    "title": division.title,
                    "slug": division.slug,
                    "draft": division.draft,
                    "team_count": division.team_count,
                    "stages": [
                        {
                            "id": stage.pk,
                            "title": stage.title,
                            "order": stage.order,
                            "keep_ladder": stage.keep_ladder,
                            "pools": [_ref(pool) for pool in stage.pools.all()],
                        }
                        for stage in division.stages.all()
                    ],
                }
                for division in divisions
            ],
            "venues": [
                {
                    "id": venue.pk,
                    "title": venue.title,
                    "timezone": _tzname(venue.timezone),
                    "grounds": [_ref(ground) for ground in venue.grounds.all()],
                }
                for venue in season.venues.prefetch_related("grounds").order_by("order")
            ],
        }

    def list_teams(
        self,
        season_id: int | None = None,
        division_id: int | None = None,
        club_id: int | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        List teams, narrowed by season, division, club and/or a name
        ``query`` (every word must appear in the team, club or division
        title). At least one filter is required. Most recent season first.

        Use it to turn "Australia Women's" into a team identifier, or to see
        every team a club has entered in a season.
        """
        limit = _clamp(limit, 100, MAX_LIMIT)
        if season_id is None and division_id is None and club_id is None and not query:
            return {
                "error": "Provide at least one of season_id, division_id, club_id or query."
            }
        teams = self._visible_teams()
        if season_id is not None:
            teams = teams.filter(division__season_id=season_id)
        if division_id is not None:
            teams = teams.filter(division_id=division_id)
        if club_id is not None:
            teams = teams.filter(club_id=club_id)
        if query:
            teams = teams.filter(
                _words_query(query, ["title", "club__title", "division__title"])
            )
        total = teams.count()
        return {
            "total": total,
            "teams": [
                {
                    "team": _team_ref(team),
                    "division": _ref(team.division),
                    "season": _ref(team.division.season),
                    "competition": _ref(team.division.season.competition),
                }
                for team in teams[:limit]
            ],
        }

    def get_team(self, team_id: int) -> dict[str, Any]:
        """
        Describe one team: its club, division, season and competition, its
        next match and last match (byes excluded), and its position on each
        ladder it appears on.

        This is the quickest way to answer "when do Australia play next?"
        or "where are we on the ladder?" once you have the team identifier.
        """
        team = self._get_team(team_id)
        if team is None:
            return {"error": f"Team {team_id} was not found."}

        now, today = self._now()
        ladders = []
        for entry in (
            team.ladder_summary.filter(stage__keep_ladder=True)
            .select_related("stage", "stage_group")
            .order_by("stage__order")
        ):
            peers = entry.stage.ladder_summary
            if entry.stage_group_id is not None:
                peers = peers.filter(stage_group_id=entry.stage_group_id)
            ordered = list(peers.values_list("pk", flat=True))
            ladders.append(
                {
                    "stage": _ref(entry.stage),
                    "pool": _ref(entry.stage_group),
                    "position": ordered.index(entry.pk) + 1,
                    "teams": len(ordered),
                    "played": entry.played,
                    "win": entry.win,
                    "loss": entry.loss,
                    "draw": entry.draw,
                    "points": float(entry.points),
                }
            )

        return {
            "team": _team_ref(team),
            "club": _ref(team.club),
            "division": _ref(team.division),
            "pool": _ref(team.stage_group),
            "season": _ref(team.division.season),
            "competition": _ref(team.division.season.competition),
            "next_match": self._next_match(team, now, today),
            "last_match": self._last_match(team, now, today),
            "ladders": ladders,
        }

    # -- schedule and results tools --------------------------------------

    def list_matches(
        self,
        competition_id: int | None = None,
        season_id: int | None = None,
        division_id: int | None = None,
        stage_id: int | None = None,
        team_id: int | None = None,
        club_id: int | None = None,
        opponent_team_id: int | None = None,
        opponent_club_id: int | None = None,
        venue_id: int | None = None,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
        status: MatchStatus = "any",
        live_stream_only: bool = False,
        include_byes: bool = True,
        order: Literal["asc", "desc"] = "asc",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        List matches (fixtures and results) matching every filter given.

        Filters: ``competition_id``, ``season_id``, ``division_id``,
        ``stage_id`` and ``venue_id`` narrow the structure; ``team_id`` or
        ``club_id`` selects matches involving that team or any team of that
        club on either side; ``opponent_team_id`` or ``opponent_club_id``
        requires the other side to match too, so "Australia v New Zealand"
        is ``club_id`` + ``opponent_club_id``; ``date_from`` and ``date_to``
        (YYYY-MM-DD) bound the match date; ``status`` is "upcoming" (not yet
        kicked off), "past" (kicked off), "completed" (result recorded) or
        "any"; ``live_stream_only`` keeps only live streamed matches.

        Results are ordered by kick-off (``order`` "desc" for most recent
        first, useful with status "completed"), paged with ``limit`` and
        ``offset``, and ``total`` reports how many matched overall. Each
        match carries its local kick-off time and time zone, venue and
        ground, both teams (undecided teams have a title but no id), scores,
        status, winner and live stream details. Use ``count_matches`` when
        you only need numbers.
        """
        limit = _clamp(limit, DEFAULT_LIMIT, MAX_LIMIT)
        offset = _clamp(offset, 0, 10**9, minimum=0)
        matches = self._filter_matches(
            self._visible_matches(),
            competition_id=competition_id,
            season_id=season_id,
            division_id=division_id,
            stage_id=stage_id,
            team_id=team_id,
            club_id=club_id,
            opponent_team_id=opponent_team_id,
            opponent_club_id=opponent_club_id,
            venue_id=venue_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
            live_stream_only=live_stream_only,
            include_byes=include_byes,
        )
        total = matches.count()
        if order == "desc":
            ordering = (F("datetime").desc(nulls_last=True), "-date", "-time", "-pk")
        else:
            ordering = (F("datetime").asc(nulls_last=True), "date", "time", "pk")
        now, today = self._now()
        rows = [
            _match_summary(match, now, today)
            for match in self._detailed(matches).order_by(*ordering)[
                offset : offset + limit
            ]
        ]
        return {
            "total": total,
            "count": len(rows),
            "offset": offset,
            "limit": limit,
            "matches": rows,
        }

    def count_matches(
        self,
        group_by: MatchGroupBy | None = None,
        competition_id: int | None = None,
        season_id: int | None = None,
        division_id: int | None = None,
        stage_id: int | None = None,
        team_id: int | None = None,
        club_id: int | None = None,
        opponent_team_id: int | None = None,
        opponent_club_id: int | None = None,
        venue_id: int | None = None,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
        status: MatchStatus = "any",
        live_stream_only: bool = False,
        include_byes: bool = True,
    ) -> dict[str, Any]:
        """
        Count matches, optionally broken down by ``group_by``: "competition",
        "season", "division", "stage", "pool", "date", "venue",
        "live_stream" or "status". Takes the same filters as
        ``list_matches``.

        Every group reports ``count`` plus how many of those are
        ``completed`` and ``live_streamed``, so "how many Men's games versus
        Women's games are being live streamed at the Euros?" is a single
        call with ``season_id`` and ``group_by="division"``.
        """
        matches = self._filter_matches(
            self._visible_matches(annotated=False),
            competition_id=competition_id,
            season_id=season_id,
            division_id=division_id,
            stage_id=stage_id,
            team_id=team_id,
            club_id=club_id,
            opponent_team_id=opponent_team_id,
            opponent_club_id=opponent_club_id,
            venue_id=venue_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
            live_stream_only=live_stream_only,
            include_byes=include_byes,
        )
        aggregates = {
            "count": Count("id"),
            "completed": Count(
                "id",
                filter=Q(home_team_score__isnull=False, away_team_score__isnull=False),
            ),
            "live_streamed": Count("id", filter=Q(live_stream=True)),
        }
        res = matches.aggregate(**aggregates)
        res["group_by"] = group_by
        res["groups"] = []
        if group_by is None:
            return res

        if group_by == "status":
            now, today = self._now()
            groups = {}
            for match in matches.only(
                "is_bye",
                "is_washout",
                "is_forfeit",
                "home_team_score",
                "away_team_score",
                "datetime",
                "date",
                "live_stream",
            ):
                status_key = _match_status(match, now, today)
                group = groups.setdefault(
                    status_key,
                    {
                        "id": status_key,
                        "title": status_key,
                        "count": 0,
                        "completed": 0,
                        "live_streamed": 0,
                    },
                )
                group["count"] += 1
                group["completed"] += status_key == "completed"
                group["live_streamed"] += match.live_stream
            res["groups"] = sorted(groups.values(), key=lambda g: g["title"])
            return res

        if group_by == "venue":
            matches = matches.annotate(
                group_id=Coalesce("play_at__ground__venue_id", "play_at_id"),
                group_title=Coalesce("play_at__ground__venue__title", "play_at__title"),
            )
            ordering = ("group_title",)
        elif group_by == "date":
            matches = matches.annotate(group_id=F("date"), group_title=F("date"))
            ordering = ("group_id",)
        elif group_by == "live_stream":
            matches = matches.annotate(
                group_id=F("live_stream"), group_title=F("live_stream")
            )
            ordering = ("-group_id",)
        else:
            path = {
                "competition": "stage__division__season__competition",
                "season": "stage__division__season",
                "division": "stage__division",
                "stage": "stage",
                "pool": "stage_group",
            }[group_by]
            matches = matches.annotate(
                group_id=F(f"{path}_id"), group_title=F(f"{path}__title")
            )
            ordering = (f"{path}__order", "group_title")

        for row in (
            matches.values("group_id", "group_title")
            .annotate(**aggregates)
            .order_by(*ordering)
        ):
            group_id = row["group_id"]
            group_title = row["group_title"]
            if isinstance(group_id, datetime.date):
                group_id = group_id.isoformat()
            if isinstance(group_title, datetime.date):
                group_title = group_title.isoformat()
            if group_by == "live_stream":
                group_title = "live streamed" if group_id else "not live streamed"
            res["groups"].append(
                {
                    "id": group_id,
                    "title": group_title,
                    "count": row["count"],
                    "completed": row["completed"],
                    "live_streamed": row["live_streamed"],
                }
            )
        return res

    def get_match(self, match_id: int) -> dict[str, Any]:
        """
        Full detail of one match by its identifier: teams, local kick-off
        time, venue and ground with coordinates and time zone, scores and
        result, live stream and video links.
        """
        match = self._detailed(self._visible_matches()).filter(pk=match_id).first()
        if match is None:
            return {"error": f"Match {match_id} was not found."}
        now, today = self._now()
        res = _match_summary(match, now, today)
        res.update(_place(match.play_at, detail=True))
        res["is_bye"] = match.is_bye
        res["is_forfeit"] = match.is_forfeit
        res["is_washout"] = match.is_washout
        return res

    def get_ladder(
        self, division_id: int | None = None, stage_id: int | None = None
    ) -> dict[str, Any]:
        """
        Standings for a division (every stage that keeps a ladder, each
        split into its pools) or for a single stage. Entries are in ladder
        order with position, played, win/loss/draw, byes, forfeits, score
        for and against, difference, percentage, bonus points and points.

        Answers "who is top of Pool A?", "did we make the top four?" and
        "what is the points difference between ...".
        """
        if division_id is None and stage_id is None:
            return {"error": "Provide a division_id or a stage_id."}
        stages = self._visible_stages().filter(keep_ladder=True)
        if stage_id is not None:
            stages = stages.filter(pk=stage_id)
        if division_id is not None:
            stages = stages.filter(division_id=division_id)
        stages = list(stages.order_by("division__order", "order"))
        if not stages:
            return {"error": "No ladder was found for the given division or stage."}

        division = stages[0].division
        res = {
            "division": _ref(division),
            "season": _ref(division.season),
            "competition": _ref(division.season.competition),
            "stages": [],
        }
        for stage in stages:
            pools = list(stage.pools.order_by("order"))
            tables = []
            if pools:
                for pool in pools:
                    entries = pool.ladder_summary.select_related("team__club")
                    tables.append(
                        {
                            "pool": _ref(pool),
                            "ladder": [
                                _ladder_entry(position, entry)
                                for position, entry in enumerate(entries, start=1)
                            ],
                        }
                    )
            else:
                entries = stage.ladder_summary.select_related("team__club")
                tables.append(
                    {
                        "pool": None,
                        "ladder": [
                            _ladder_entry(position, entry)
                            for position, entry in enumerate(entries, start=1)
                        ],
                    }
                )
            res["stages"].append({"stage": _ref(stage), "pools": tables})
        return res

    # -- identity --------------------------------------------------------

    def whoami(self) -> dict[str, Any]:
        """
        Identify the connected user so "my" questions can be answered, for
        example "when is my next game?" or "how did we go?": their name,
        the person record and club they are linked to, and the teams they
        are registered with (most recent season first), each with its next
        and last match.

        When ``authenticated`` is false the caller is anonymous: ask which
        team or club they follow and use ``search`` instead. Superusers can
        also see divisions still in draft.
        """
        user = self._user()
        if user is None or not getattr(user, "is_authenticated", False):
            return {
                "authenticated": False,
                "message": (
                    "The MCP client is not authenticated, so there is no "
                    "'me'. Ask which team or club the person follows."
                ),
            }

        now, today = self._now()
        res = {
            "authenticated": True,
            "username": user.get_username(),
            "name": getattr(user, "get_full_name", lambda: "")() or None,
            "is_superuser": bool(user.is_superuser),
            "person": None,
            "club": None,
            "teams": [],
        }
        person = Person.objects.filter(user=user).select_related("club").first()
        if person is None:
            res["message"] = (
                "This user is not linked to a person in the competition "
                "system, so no team registrations are known."
            )
            return res

        res["person"] = {
            "id": str(person.pk),
            "name": f"{person.first_name} {person.last_name}",
        }
        res["club"] = _ref(person.club)
        teams = (
            self._visible_teams()
            .filter(people__person=person)
            .select_related("stage_group")
            .distinct()
        )
        for team in teams[:20]:
            res["teams"].append(
                {
                    "team": _team_ref(team),
                    "division": _ref(team.division),
                    "pool": _ref(team.stage_group),
                    "season": _ref(team.division.season),
                    "competition": _ref(team.division.season.competition),
                    "next_match": self._next_match(team, now, today),
                    "last_match": self._last_match(team, now, today),
                }
            )
        return res


def _tool(toolset_class, name):
    """
    Publish ``toolset_class.<name>`` as an async tool.

    Tools run on the event loop the view drives, so the synchronous ORM code
    is pushed back to the request thread with ``sync_to_async``; that keeps
    database connections (and test transactions) on the thread Django
    expects. The wrapper borrows the method's signature and docstring so the
    SDK derives the tool's schema and description from them.
    """
    method = getattr(toolset_class, name)

    @functools.wraps(method)
    async def tool(**kwargs):
        toolset = toolset_class(request=current_request.get(None))
        return await sync_to_async(getattr(toolset, name))(**kwargs)

    # Drop ``self`` from the published signature.
    parameters = list(inspect.signature(method).parameters.values())[1:]
    tool.__signature__ = inspect.Signature(
        parameters, return_annotation=inspect.signature(method).return_annotation
    )
    return tool


# Human readable titles where the one derived from the method name reads
# poorly; everything else becomes "Upcoming events", "Get ladder" and so on.
TOOL_TITLES = {
    "whoami": "Who am I",
}

# Every tool only reads the database. Saying so lets clients such as Claude
# and ChatGPT run them without asking the user to approve each call, and the
# connector directories refuse listings whose tools carry no annotations.
TOOL_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def build_server(name=None, instructions=None, toolset_class=CompetitionToolset):
    """
    Build an ``MCPServer`` publishing every public method of ``toolset_class``.

    ``instructions`` (typically the project's description of itself and its
    competitions) are placed ahead of the competition tool instructions so
    an agent reads the project context first.
    """
    combined = INSTRUCTIONS
    if instructions:
        combined = instructions.strip() + "\n\n" + INSTRUCTIONS
    server = MCPServer(name=name or "tournamentcontrol", instructions=combined)
    for method_name, __ in inspect.getmembers(
        toolset_class, predicate=inspect.isfunction
    ):
        if method_name.startswith("_"):
            continue
        server.add_tool(
            _tool(toolset_class, method_name),
            name=method_name,
            title=TOOL_TITLES.get(
                method_name, method_name.replace("_", " ").capitalize()
            ),
            annotations=TOOL_ANNOTATIONS,
        )
    return server


_server = None


def get_server():
    """
    The process-wide server configured from ``TOURNAMENTCONTROL_MCP_NAME``
    and ``TOURNAMENTCONTROL_MCP_INSTRUCTIONS``.
    """
    global _server
    if _server is None:
        _server = build_server(
            name=getattr(settings, "TOURNAMENTCONTROL_MCP_NAME", None),
            instructions=getattr(settings, "TOURNAMENTCONTROL_MCP_INSTRUCTIONS", None),
        )
    return _server
