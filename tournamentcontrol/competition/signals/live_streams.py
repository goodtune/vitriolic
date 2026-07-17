import logging

from django.db import transaction

from tournamentcontrol.competition.tasks import (
    delete_youtube_broadcast,
    delete_youtube_stream,
)

logger = logging.getLogger(__name__)


def _season_credentials(instance):
    """Return the instance's season when its YouTube credentials are set."""
    season = instance.season
    if season.live_stream_client_id and season.live_stream_client_secret:
        return season
    return None


def cleanup_youtube_broadcast(sender, instance, **kwargs):
    """
    When a LiveStreamEvent is deleted, remove its scheduled broadcast from
    the YouTube platform too.
    """
    season = _season_credentials(instance)
    if season is None or not instance.external_identifier:
        return
    external_identifier = instance.external_identifier
    transaction.on_commit(
        lambda: delete_youtube_broadcast.s(
            season.pk, external_identifier
        ).apply_async()
    )


def cleanup_youtube_stream(sender, instance, **kwargs):
    """
    When a LiveStreamKey is deleted, remove its liveStream resource from
    the YouTube platform too.
    """
    season = _season_credentials(instance)
    if season is None or not instance.external_identifier:
        return
    external_identifier = instance.external_identifier
    transaction.on_commit(
        lambda: delete_youtube_stream.s(season.pk, external_identifier).apply_async()
    )
