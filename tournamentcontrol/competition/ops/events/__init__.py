"""
Event bus for the ops site.

Sync code (views, signal receivers, Celery tasks) calls ``publish``; the
SSE views consume ``subscribe``. The backend is the class named by the
``OPS_EVENTS_BACKEND`` setting, instantiated with ``OPS_EVENTS_OPTIONS``:
``memory.MemoryBackend`` for one process (tests, local development) and
``redis.RedisBackend`` for many workers.
"""

import logging
import threading

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from tournamentcontrol.competition.ops.default_settings import (
    EVENTS_BACKEND,
    EVENTS_OPTIONS,
)
from tournamentcontrol.competition.ops.events.base import Backend
from tournamentcontrol.competition.ops.events.memory import MemoryBackend
from tournamentcontrol.competition.ops.events.redis import RedisBackend

__all__ = (
    "Backend",
    "MemoryBackend",
    "RedisBackend",
    "get_backend",
    "publish",
    "recent",
    "reset_backend",
    "subscribe",
)

logger = logging.getLogger(__name__)

_backend = None
_lock = threading.Lock()


def get_backend():
    global _backend
    with _lock:
        if _backend is None:
            path = str(EVENTS_BACKEND)
            try:
                backend_class = import_string(path)
            except ImportError as exc:
                raise ImproperlyConfigured(
                    "OPS_EVENTS_BACKEND %r cannot be imported: %s" % (path, exc)
                ) from exc
            try:
                _backend = backend_class(**dict(EVENTS_OPTIONS))
            except TypeError as exc:
                raise ImproperlyConfigured(
                    "OPS_EVENTS_OPTIONS do not suit %s: %s" % (path, exc)
                ) from exc
        return _backend


def reset_backend():
    global _backend
    with _lock:
        _backend = None


def publish(season_id, type, actor=None, summary="", **data):
    event = {
        "type": type,
        "season": season_id,
        "actor": actor,
        "at": timezone.now().isoformat(),
        "summary": summary,
        **data,
    }
    logger.debug("ops event %s for season %s: %s", type, season_id, summary)
    transaction.on_commit(
        lambda: get_backend().publish(season_id, event), robust=True
    )


def subscribe(season_id, idle):
    return get_backend().subscribe(season_id, idle)


def recent(season_id):
    return get_backend().recent(season_id)
