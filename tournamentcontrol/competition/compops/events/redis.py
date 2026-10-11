"""
A Redis event bus for many workers, and for the Celery refresh task.

Configure it with::

    COMPOPS_EVENTS_BACKEND = "tournamentcontrol.competition.compops.events.redis.RedisBackend"
    COMPOPS_EVENTS_OPTIONS = {"url": "redis://localhost:6379/0"}
"""

import json

import redis as redis_lib
from redis import asyncio as redis_asyncio

from tournamentcontrol.competition.compops.default_settings import ACTIVITY_LENGTH
from tournamentcontrol.competition.compops.events.base import Backend


class RedisBackend(Backend):
    def __init__(self, url, sync_client=None, async_client=None):
        self.sync = sync_client or redis_lib.Redis.from_url(url)
        self.async_client = async_client or redis_asyncio.Redis.from_url(url)

    @staticmethod
    def _channel(season_id):
        return f"compops:season:{season_id}"

    @staticmethod
    def _ring(season_id):
        return f"compops:season:{season_id}:recent"

    def publish(self, season_id, event):
        payload = json.dumps(event)
        pipe = self.sync.pipeline()
        pipe.publish(self._channel(season_id), payload)
        pipe.lpush(self._ring(season_id), payload)
        pipe.ltrim(self._ring(season_id), 0, int(ACTIVITY_LENGTH) - 1)
        pipe.execute()

    async def subscribe(self, season_id, idle):
        """
        Yield ``None`` once as soon as the subscription is registered, then an
        event dict per event, or ``None`` after ``idle`` seconds without one.
        """
        pubsub = self.async_client.pubsub()
        await pubsub.subscribe(self._channel(season_id))
        try:
            yield None
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=idle
                )
                if message is None:
                    yield None
                elif message["type"] == "message":
                    yield json.loads(message["data"])
        finally:
            try:
                await pubsub.unsubscribe(self._channel(season_id))
            finally:
                await pubsub.aclose()

    def recent(self, season_id):
        raw = self.sync.lrange(self._ring(season_id), 0, int(ACTIVITY_LENGTH) - 1)
        return [json.loads(item) for item in raw]
