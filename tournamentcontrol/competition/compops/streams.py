"""
Start, test and stop YouTube broadcasts from the ops site, and tell every
open page about it.
"""

import logging

from django.db import transaction
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError

from tournamentcontrol.competition.compops import events
from tournamentcontrol.competition.exceptions import LiveStreamError
from tournamentcontrol.competition.models import LiveStreamEvent, Match

logger = logging.getLogger(__name__)

STATUSES = ("testing", "live", "complete")

# YouTube reports these while a transition is under way; the broadcast is, for
# every purpose of the ops site, already in the state it is moving to.
TRANSIENT = {"liveStarting": "live", "testStarting": "testing"}


def effective_status(status):
    """The status to act and render on, mapping YouTube's transient ones."""
    return TRANSIENT.get(status, status)


def describe(obj):
    if isinstance(obj, Match):
        ground = obj.play_at.title if obj.play_at else "No ground"
        return f"{ground} · {obj.get_home_team_plain()} v {obj.get_away_team_plain()}"
    return obj.title


def season_of(obj):
    if isinstance(obj, Match):
        return obj.stage.division.season
    return obj.season


def publish_change(obj, status, actor):
    kind = "match" if isinstance(obj, Match) else "event"
    events.publish(
        season_of(obj).pk,
        "stream-changed",
        actor=actor,
        summary=f"{describe(obj)} → {status}",
        kind=kind,
        id=obj.pk,
        status=status,
    )


def _lock(obj):
    """
    Re-read ``obj`` (a Match or LiveStreamEvent) and lock its row until the
    end of the current transaction. Must be called inside one.
    """
    if isinstance(obj, Match):
        # The default manager annotates team titles through outer joins that
        # a row lock cannot be taken across.
        queryset = Match._base_manager.select_related(
            "stage__division__season__competition",
            "play_at",
            "home_team",
            "away_team",
        )
    else:
        queryset = LiveStreamEvent.objects.select_related("season__competition")
    return queryset.select_for_update(of=("self",)).get(pk=obj.pk)


def _transition_locked(obj, status):
    """
    Transition the locked row of ``obj``, so two operators (or an operator
    and the status refresh) acting on the same broadcast are serialised and
    neither overwrites the other with a status read before it changed. The
    caller's ``obj`` is brought up to date for rendering.
    """
    with transaction.atomic():
        locked = _lock(obj)
        locked.transition_live_stream(status)
    obj.live_stream_status = locked.live_stream_status
    obj.live_stream_status_at = locked.live_stream_status_at


def transition(obj, status, actor):
    """
    Transition ``obj`` (a Match or LiveStreamEvent) and publish the change.
    Returns an error message for the page when the transition fails.
    """
    try:
        _transition_locked(obj, status)
    except type(obj).DoesNotExist:
        logger.warning("compops stream transition for %s: row is gone", obj)
        return f"{describe(obj)}: no longer exists"
    except LiveStreamError as exc:
        logger.warning("compops stream transition refused for %s: %s", obj, exc)
        return f"{describe(obj)}: {exc}"
    except HttpError as exc:
        logger.warning("compops stream transition failed for %s: %s", obj, exc.reason)
        return f"{describe(obj)}: {exc.reason}"
    except (RefreshError, TransportError) as exc:
        logger.exception("compops stream transition failed for %s", obj)
        return f"{describe(obj)}: {exc}"
    publish_change(obj, status, actor)
    return None
