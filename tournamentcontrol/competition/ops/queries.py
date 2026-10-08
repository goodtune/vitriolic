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
from tournamentcontrol.competition.utils import team_needs_progressing

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


def has_result(match):
    if match.is_bye:
        return match.bye_processed
    return (
        (match.home_team_score is not None and match.away_team_score is not None)
        or match.is_forfeit
        or match.is_washout
    )


def editable(match):
    if match.mysideline_id is not None:
        return False
    if match.is_bye:
        return True
    needs_progressing = Match.objects.filter(team_needs_progressing, pk=match.pk)
    return not needs_progressing.exists()


def day_matches(season, day):
    return (
        Match.objects.filter(stage__division__season=season, date=day)
        .select_related(*SELECT_RELATED)
        .order_by("time", "play_at__order", "pk")
    )


def _slot_state(matches):
    entered = sum(1 for m in matches if has_result(m))
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


def local_today(place_or_season, now):
    tzinfo = getattr(place_or_season, "timezone", None)
    if tzinfo is None and isinstance(place_or_season, Ground):
        tzinfo = place_or_season.venue.timezone or place_or_season.venue.season.timezone
    if tzinfo is None:
        tzinfo = timezone.get_current_timezone()
    return timezone.localtime(now, tzinfo).date()


def _ground_matches(ground, day):
    return (
        Match.objects.filter(play_at=ground, date=day, is_bye=False)
        .exclude(time=None)
        .select_related(*SELECT_RELATED)
        .order_by("time", "pk")
    )


def ground_day(ground, day, now):
    local = timezone.localtime(now, ground.timezone or ground.venue.timezone).time()
    matches = list(_ground_matches(ground, day))
    started = [m for m in matches if m.time <= local]
    upcoming = [m for m in matches if m.time > local]
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
        datetime.datetime.combine(day, datetime.time.min), season.timezone
    )
    end = start + datetime.timedelta(days=1)
    events = LiveStreamEvent.objects.filter(
        season=season, start__gte=start, start__lt=end
    ).order_by("start")
    return streams, events
