"""
Keep the stored YouTube broadcast status current, so a change made in
YouTube Studio reaches the ops page and the booth lamp.
"""

import datetime
import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from tournamentcontrol.competition.compops import streams
from tournamentcontrol.competition.models import LiveStreamEvent, Match

logger = logging.getLogger(__name__)

BATCH = 50


def broadcasts_today(season, now):
    day = season.local_date(now)
    # A match turned off for streaming can keep its identifier until the
    # broadcast is removed; it is no longer one of the day's broadcasts.
    matches = Match.objects.filter(
        stage__division__season=season,
        date=day,
        live_stream=True,
        external_identifier__isnull=False,
    ).select_related("stage__division__season", "play_at", "home_team", "away_team")
    start = timezone.make_aware(
        datetime.datetime.combine(day, datetime.time.min), season.get_tzinfo()
    )
    # A removed event (``live_stream=False``) has no broadcast left to poll.
    live_events = LiveStreamEvent.objects.filter(
        season=season,
        live_stream=True,
        start__gte=start,
        start__lt=start + datetime.timedelta(days=1),
    ).select_related("season")
    return list(matches) + list(live_events)


def _store_if_current(obj, status, now):
    """
    Store the polled ``status`` of ``obj`` under a lock on its row, unless the
    row already has it or was changed after the poll began at ``now`` (a
    manual transition that landed meanwhile is newer than what was polled).
    Returns whether the row was written.
    """
    # The default manager annotates team titles through outer joins that a
    # row lock cannot be taken across.
    manager = Match._base_manager if isinstance(obj, Match) else LiveStreamEvent.objects
    with transaction.atomic():
        try:
            locked = (
                manager.select_for_update(of=("self",))
                .only("live_stream_status", "live_stream_status_at")
                .get(pk=obj.pk)
            )
        except ObjectDoesNotExist:
            return False
        if locked.live_stream_status == status:
            return False
        if locked.live_stream_status_at and locked.live_stream_status_at > now:
            return False
        locked._store_live_stream_status(status, now)
    obj.live_stream_status = locked.live_stream_status
    obj.live_stream_status_at = locked.live_stream_status_at
    return True


def refresh_season_status(season, now=None, youtube=None):
    now = now or timezone.now()
    objects = broadcasts_today(season, now)
    if not objects:
        return 0
    service = youtube or season.youtube
    statuses = {}
    for offset in range(0, len(objects), BATCH):
        ids = [o.external_identifier for o in objects[offset : offset + BATCH]]
        response = (
            service.liveBroadcasts()
            .list(part="status", id=",".join(ids), maxResults=BATCH)
            .execute()
        )
        for item in response.get("items", []):
            statuses[item["id"]] = item["status"]["lifeCycleStatus"]
    changed = 0
    for obj in objects:
        new_status = statuses.get(obj.external_identifier)
        if not new_status or new_status == obj.live_stream_status:
            continue
        if not _store_if_current(obj, new_status, now):
            continue
        streams.publish_change(obj, new_status, actor="youtube")
        changed += 1
    logger.info("refreshed %d broadcast statuses for season %s", changed, season.pk)
    return changed
