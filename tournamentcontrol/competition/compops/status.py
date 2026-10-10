"""
Keep the stored YouTube broadcast status current, so a change made in
YouTube Studio reaches the ops page and the booth lamp.
"""

import datetime
import logging

from django.utils import timezone

from tournamentcontrol.competition.compops import streams
from tournamentcontrol.competition.models import LiveStreamEvent, Match

logger = logging.getLogger(__name__)

BATCH = 50


def broadcasts_today(season, now):
    day = season.local_date(now)
    matches = Match.objects.filter(
        stage__division__season=season, date=day, external_identifier__isnull=False
    ).select_related("stage__division__season", "play_at", "home_team", "away_team")
    start = timezone.make_aware(
        datetime.datetime.combine(day, datetime.time.min), season.get_tzinfo()
    )
    live_events = LiveStreamEvent.objects.filter(
        season=season, start__gte=start, start__lt=start + datetime.timedelta(days=1)
    ).select_related("season")
    return list(matches) + list(live_events)


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
        obj._store_live_stream_status(new_status, now)
        streams.publish_change(obj, new_status, actor="youtube")
        changed += 1
    logger.info("refreshed %d broadcast statuses for season %s", changed, season.pk)
    return changed
