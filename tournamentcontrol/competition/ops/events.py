"""
Event bus for the ops site.

Sync code (views, signal receivers, Celery tasks) calls ``publish``; the
SSE views consume ``subscribe``. Two backends: ``memory`` for one process
(tests, local development) and ``redis`` for many workers.
"""

import asyncio
import collections
import json
import logging
import threading

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

_backend = None
_lock = threading.Lock()


def _activity_length():
    return getattr(settings, "OPS_ACTIVITY_LENGTH", 50)


class MemoryBackend:
    def __init__(self):
        self._subscribers = collections.defaultdict(set)
        self._recent = collections.defaultdict(collections.deque)

    def publish(self, season_id, event):
        ring = self._recent[season_id]
        ring.appendleft(event)
        while len(ring) > _activity_length():
            ring.pop()
        for loop, queue in list(self._subscribers[season_id]):
            loop.call_soon_threadsafe(queue.put_nowait, event)

    async def subscribe(self, season_id, idle):
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        key = (loop, queue)
        self._subscribers[season_id].add(key)
        try:
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), idle)
                except asyncio.TimeoutError:
                    yield None
        finally:
            self._subscribers[season_id].discard(key)

    def recent(self, season_id):
        return list(self._recent[season_id])[: _activity_length()]


class RedisBackend:
    def __init__(self, url, sync_client=None, async_client=None):
        import redis
        import redis.asyncio

        self.sync = sync_client or redis.Redis.from_url(url)
        self.async_client = async_client or redis.asyncio.Redis.from_url(url)

    @staticmethod
    def _channel(season_id):
        return f"ops:season:{season_id}"

    @staticmethod
    def _ring(season_id):
        return f"ops:season:{season_id}:recent"

    def publish(self, season_id, event):
        payload = json.dumps(event)
        pipe = self.sync.pipeline()
        pipe.publish(self._channel(season_id), payload)
        pipe.lpush(self._ring(season_id), payload)
        pipe.ltrim(self._ring(season_id), 0, _activity_length() - 1)
        pipe.execute()

    async def subscribe(self, season_id, idle):
        pubsub = self.async_client.pubsub()
        await pubsub.subscribe(self._channel(season_id))
        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=idle
                )
                if message is None:
                    yield None
                elif message["type"] == "message":
                    yield json.loads(message["data"])
        finally:
            await pubsub.unsubscribe(self._channel(season_id))
            await pubsub.aclose()

    def recent(self, season_id):
        raw = self.sync.lrange(self._ring(season_id), 0, _activity_length() - 1)
        return [json.loads(item) for item in raw]


def get_backend():
    global _backend
    with _lock:
        if _backend is None:
            name = getattr(settings, "OPS_EVENTS_BACKEND", "memory")
            if name == "redis":
                url = getattr(settings, "OPS_EVENTS_REDIS_URL", None)
                if not url:
                    raise ValueError(
                        "OPS_EVENTS_REDIS_URL is required when "
                        "OPS_EVENTS_BACKEND is 'redis'"
                    )
                _backend = RedisBackend(url)
            else:
                _backend = MemoryBackend()
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
    transaction.on_commit(lambda: get_backend().publish(season_id, event))


def subscribe(season_id, idle):
    return get_backend().subscribe(season_id, idle)


def recent(season_id):
    return get_backend().recent(season_id)
