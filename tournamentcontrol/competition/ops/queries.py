"""
Read-side helpers for the ops site. Pure functions over the ORM; no
request objects, no rendering.
"""

import dataclasses
import datetime

from django.db.models import F, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from tournamentcontrol.competition.models import (
    Ground,
    LiveStreamEvent,
    Match,
    SimpleScoreMatchStatistic,
)

SELECT_RELATED = (
    "stage__division__season",
    "play_at",
    "home_team__club",
    "away_team__club",
    "home_team_undecided",
    "away_team_undecided",
)


@dataclasses.dataclass
class Slot:
    key: str
    time: datetime.time | None
    label: str
    matches: list
    state: str = "pending"
    entered: int = 0
    total: int = 0
    open: bool = False
    is_byes: bool = False


@dataclasses.dataclass
class GroundStreams:
    ground: Ground
    current: Match | None
    next: Match | None


def day_matches(season, day):
    return (
        Match.objects.filter(stage__division__season=season, date=day)
        .select_related(*SELECT_RELATED)
        .with_result_state()
        .order_by("time", "play_at__order", "pk")
    )


def _slot_state(matches):
    entered = sum(1 for m in matches if m.has_result)
    if entered == len(matches):
        return "complete", entered
    if entered:
        return "in_progress", entered
    return "pending", entered


def day_results(season, day):
    timed = {}
    unscheduled = []
    byes = []
    for match in day_matches(season, day):
        if match.is_bye:
            byes.append(match)
        elif match.time is None:
            unscheduled.append(match)
        else:
            timed.setdefault(match.time, []).append(match)

    slots = []
    for time, matches in sorted(timed.items()):
        slots.append(Slot(time.strftime("%H%M"), time, time.strftime("%H:%M"), matches))
    if unscheduled:
        slots.append(Slot("unscheduled", None, "Unscheduled", unscheduled))
    for slot in slots:
        slot.state, slot.entered = _slot_state(slot.matches)
        slot.total = len(slot.matches)
    for slot in slots:
        if slot.state != "complete":
            slot.open = True
            break
    if byes:
        state, entered = _slot_state(byes)
        slots.append(
            Slot("byes", None, "Byes", byes, state, entered, len(byes), False, True)
        )
    return slots


def slot_for(season, day, slot_key):
    for slot in day_results(season, day):
        if slot.key == slot_key:
            return slot
    return None


def _team_points(side):
    """
    Sum of recorded points for one side of the match, 0 when no statistic
    rows exist for that side (NULL would make the balance test unknowable).
    """
    stats = SimpleScoreMatchStatistic.objects.filter(
        match=OuterRef("pk"), player__teamassociation__team=OuterRef(f"{side}_team")
    ).order_by()
    total = stats.values("match").annotate(total=Sum("points")).values("total")
    return Coalesce(Subquery(total), 0)


def day_scorers(season, day):
    if not season.statistics:
        return Match.objects.none()
    return (
        day_matches(season, day)
        .filter(
            is_bye=False,
            is_forfeit=False,
            mysideline_id__isnull=True,
            home_team__isnull=False,
            away_team__isnull=False,
            home_team_score__isnull=False,
            away_team_score__isnull=False,
        )
        .annotate(home_points=_team_points("home"), away_points=_team_points("away"))
        .filter(
            Q(statistics__isnull=True)
            | ~Q(home_points=F("home_team_score"))
            | ~Q(away_points=F("away_team_score"))
        )
        .distinct()
    )


def out_of_balance(match):
    return match.home_points != match.home_team_score or (
        match.away_points != match.away_team_score
    )


def _ground_matches(ground, day):
    return (
        Match.objects.filter(play_at=ground, date=day, is_bye=False)
        .exclude(time=None)
        .exclude(datetime=None)
        .select_related(*SELECT_RELATED)
        .order_by("time", "pk")
    )


def ground_day(ground, day, now):
    matches = list(_ground_matches(ground, day))
    started = [m for m in matches if m.datetime <= now]
    upcoming = [m for m in matches if m.datetime > now]
    current = started[-1] if started else None
    previous = started[-2] if len(started) > 1 else None
    following = upcoming[0] if upcoming else None
    return previous, current, following


def day_streams(season, day, now):
    grounds = Ground.objects.filter(venue__season=season, live_stream=True).order_by(
        "venue__order", "order"
    )
    streams = []
    for ground in grounds:
        _, current, following = ground_day(ground, day, now)
        streams.append(GroundStreams(ground, current, following))
    start = timezone.make_aware(
        datetime.datetime.combine(day, datetime.time.min), season.get_tzinfo()
    )
    end = start + datetime.timedelta(days=1)
    events = LiveStreamEvent.objects.filter(
        season=season, start__gte=start, start__lt=end
    ).order_by("start")
    return streams, events


def team_results(team):
    return (
        Match.objects.filter(Q(home_team=team) | Q(away_team=team), is_bye=False)
        .select_related(*SELECT_RELATED)
        .order_by("datetime", "pk")
    )


def division_leaders(division, limit=10):
    base = (
        SimpleScoreMatchStatistic.objects.filter(
            match__stage__division=division,
            played=1,
            player__teamassociation__team__division=division,
        )
        .values(
            "player_id",
            "player__first_name",
            "player__last_name",
            "player__teamassociation__team__title",
        )
        .annotate(points=Sum("points"), mvp=Sum("mvp"))
    )

    def rows(queryset):
        return [
            {
                "name": "%s %s" % (r["player__first_name"], r["player__last_name"]),
                "team": r["player__teamassociation__team__title"],
                "points": r["points"] or 0,
                "mvp": r["mvp"] or 0,
            }
            for r in queryset
        ]

    scorers = rows(
        base.exclude(points=None)
        .exclude(points=0)
        .order_by("-points", "player__last_name")[:limit]
    )
    mvps = rows(
        base.exclude(mvp=None)
        .exclude(mvp=0)
        .order_by("-mvp", "player__last_name")[:limit]
    )
    return scorers, mvps


def ground_runsheet(ground, day):
    return _ground_matches(ground, day)
