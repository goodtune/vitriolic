"""
An in-process event bus: one server process only (tests, local development).
"""

import asyncio
import collections
import logging

from tournamentcontrol.competition.compops.default_settings import ACTIVITY_LENGTH
from tournamentcontrol.competition.compops.events.base import Backend

logger = logging.getLogger(__name__)


class MemoryBackend(Backend):
    def __init__(self):
        self._subscribers = collections.defaultdict(set)
        self._recent = collections.defaultdict(collections.deque)

    def publish(self, season_id, event):
        ring = self._recent[season_id]
        ring.appendleft(event)
        while len(ring) > int(ACTIVITY_LENGTH):
            ring.pop()
        for key in list(self._subscribers[season_id]):
            loop, queue = key
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError as exc:
                # The subscriber's loop has closed without unsubscribing; drop
                # it so one dead subscriber never blocks the others.
                logger.warning(
                    "dropping stale compops subscriber for season %s: %s",
                    season_id,
                    exc,
                )
                self._subscribers[season_id].discard(key)

    async def subscribe(self, season_id, idle):
        """
        Yield ``None`` once as soon as the subscription is registered, then an
        event dict per event, or ``None`` after ``idle`` seconds without one.
        """
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        key = (loop, queue)
        self._subscribers[season_id].add(key)
        try:
            yield None
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), idle)
                except asyncio.TimeoutError:
                    yield None
        finally:
            self._subscribers[season_id].discard(key)

    def recent(self, season_id):
        return list(self._recent[season_id])[: int(ACTIVITY_LENGTH)]
