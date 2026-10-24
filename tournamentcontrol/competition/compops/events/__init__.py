"""
Event bus for the ops site.

Sync code (views, signal receivers, Celery tasks) calls ``publish``; the
SSE views consume ``subscribe``. The backend is the class named by the
``COMPOPS_EVENTS_BACKEND`` setting, instantiated with ``COMPOPS_EVENTS_OPTIONS``:
``memory.MemoryBackend`` for one process (tests, local development) and
``redis.RedisBackend`` for many workers.

One bus serves every tenant of a ``django-tenant-schemas`` site, so each
season's events go to a ``channel`` that also names the tenant's schema.
``publish``, ``subscribe`` and ``recent`` read the schema from the database
connection when they are called, so call all three from sync code where the
connection points at the tenant: a view, a receiver, a task run in the
tenant's schema. The SSE views call ``subscribe`` through ``sync_to_async``.
"""

import logging
import threading

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from touchtechnology.common.utils import get_schema_name
from tournamentcontrol.competition.compops.default_settings import (
    EVENTS_BACKEND,
    EVENTS_OPTIONS,
)

__all__ = (
    "channel",
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
                    f"COMPOPS_EVENTS_BACKEND {path!r} cannot be imported: {exc}"
                ) from exc
            try:
                _backend = backend_class(**dict(EVENTS_OPTIONS))
            except TypeError as exc:
                raise ImproperlyConfigured(
                    f"COMPOPS_EVENTS_OPTIONS do not suit {path}: {exc}"
                ) from exc
        return _backend


def reset_backend():
    global _backend
    with _lock:
        _backend = None


def channel(season_id):
    """
    Name the channel of ``season_id`` in the current tenant: ``alpha:season:3``
    when the connection points at the ``alpha`` schema, and ``season:3`` on a
    single-tenant site.
    """
    schema_name = get_schema_name()
    if schema_name is None:
        return f"season:{season_id}"
    return f"{schema_name}:season:{season_id}"


def publish(season_id, type, actor=None, summary="", **data):
    event = {
        "type": type,
        "season": season_id,
        "actor": actor,
        "at": timezone.now().isoformat(),
        "summary": summary,
        **data,
    }
    name = channel(season_id)
    logger.debug("compops event %s on %s: %s", type, name, summary)
    transaction.on_commit(lambda: get_backend().publish(name, event), robust=True)


def subscribe(season_id, idle):
    """
    Return the subscription to ``season_id`` in the current tenant, an async
    generator (see ``Backend.subscribe``). The channel is named now, on the
    calling thread; the subscription is made when it is first iterated.
    """
    return get_backend().subscribe(channel(season_id), idle)


def recent(season_id):
    return get_backend().recent(channel(season_id))
