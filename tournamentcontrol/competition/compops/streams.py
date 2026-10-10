"""
Start, test and stop YouTube broadcasts from the ops site, and tell every
open page about it.
"""

import logging

from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError

from tournamentcontrol.competition.compops import events
from tournamentcontrol.competition.exceptions import LiveStreamError
from tournamentcontrol.competition.models import Match

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


def transition(obj, status, actor):
    """
    Transition ``obj`` (a Match or LiveStreamEvent) and publish the change.
    Returns an error message for the page when the transition fails.
    """
    try:
        obj.transition_live_stream(status)
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
