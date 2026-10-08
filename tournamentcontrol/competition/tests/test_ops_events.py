import asyncio

import fakeredis
from asgiref.sync import sync_to_async
from django.test import override_settings
from test_plus import TestCase

from tournamentcontrol.competition.ops import events


class MemoryBackendTests(TestCase):
    def setUp(self):
        events.reset_backend()

    def tearDown(self):
        events.reset_backend()

    def publish_committed(self, *args, **kwargs):
        # ``publish`` defers to ``transaction.on_commit``, which touches the
        # database connection, so async tests must call it from a thread.
        with self.captureOnCommitCallbacks(execute=True):
            events.publish(*args, **kwargs)

    def test_recent_is_newest_first_and_bounded(self):
        with override_settings(OPS_ACTIVITY_LENGTH=2):
            events.reset_backend()
            with self.captureOnCommitCallbacks(execute=True):
                for n in range(3):
                    events.publish(1, "score-entered", actor="gary", match=n)
        types = [e["match"] for e in events.recent(1)]
        self.assertEqual(types, [2, 1])

    def test_event_shape(self):
        with self.captureOnCommitCallbacks(execute=True):
            events.publish(
                7, "stream-changed", actor="gary", summary="Field 1 live", id=3
            )
        (event,) = events.recent(7)
        self.assertEqual(event["type"], "stream-changed")
        self.assertEqual(event["season"], 7)
        self.assertEqual(event["actor"], "gary")
        self.assertEqual(event["summary"], "Field 1 live")
        self.assertEqual(event["id"], 3)
        self.assertTrue(event["at"].endswith("+00:00"))

    async def test_subscribe_receives_published_event(self):
        async def consume():
            async for event in events.subscribe(1, idle=0.05):
                if event is not None:
                    return event

        task = asyncio.ensure_future(consume())
        await asyncio.sleep(0.01)
        await sync_to_async(self.publish_committed)(1, "score-entered", match=5)
        event = await asyncio.wait_for(task, timeout=2)
        self.assertEqual(event["match"], 5)

    async def test_subscribe_yields_none_when_idle(self):
        async def first():
            async for event in events.subscribe(1, idle=0.01):
                return event

        self.assertIsNone(await asyncio.wait_for(first(), timeout=2))

    async def test_other_season_not_delivered(self):
        async def consume():
            seen = []
            async for event in events.subscribe(1, idle=0.05):
                if event is None:
                    return seen
                seen.append(event)

        task = asyncio.ensure_future(consume())
        await asyncio.sleep(0.01)
        await sync_to_async(self.publish_committed)(2, "score-entered", match=5)
        self.assertEqual(await asyncio.wait_for(task, timeout=2), [])


class RedisBackendTests(TestCase):
    def setUp(self):
        self.server = fakeredis.FakeServer()
        self.backend = events.RedisBackend(
            "redis://unused",
            sync_client=fakeredis.FakeRedis(server=self.server),
            async_client=fakeredis.FakeAsyncRedis(server=self.server),
        )

    def test_recent_uses_a_bounded_list(self):
        with override_settings(OPS_ACTIVITY_LENGTH=2):
            for n in range(3):
                self.backend.publish(1, {"type": "x", "match": n})
        self.assertEqual([e["match"] for e in self.backend.recent(1)], [2, 1])

    async def test_pubsub_round_trip(self):
        async def consume():
            async for event in self.backend.subscribe(1, idle=0.05):
                if event is not None:
                    return event

        task = asyncio.ensure_future(consume())
        await asyncio.sleep(0.05)
        self.backend.publish(1, {"type": "score-entered", "match": 9})
        event = await asyncio.wait_for(task, timeout=2)
        self.assertEqual(event["match"], 9)


class BackendSelectionTests(TestCase):
    def tearDown(self):
        events.reset_backend()

    def test_default_is_memory(self):
        events.reset_backend()
        self.assertIsInstance(events.get_backend(), events.MemoryBackend)

    @override_settings(
        OPS_EVENTS_BACKEND="redis", OPS_EVENTS_REDIS_URL="redis://localhost/0"
    )
    def test_redis_selected_by_setting(self):
        events.reset_backend()
        self.assertIsInstance(events.get_backend(), events.RedisBackend)

    @override_settings(OPS_EVENTS_BACKEND="redis", OPS_EVENTS_REDIS_URL=None)
    def test_redis_without_url_is_an_error(self):
        events.reset_backend()
        with self.assertRaises(ValueError):
            events.get_backend()
