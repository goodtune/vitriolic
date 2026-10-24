import asyncio
import contextlib
from unittest import mock

import fakeredis
from asgiref.sync import sync_to_async
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from test_plus import TestCase

from touchtechnology.admin.tests.tenancy import schema_context
from tournamentcontrol.competition.compops import events
from tournamentcontrol.competition.compops.events.memory import MemoryBackend
from tournamentcontrol.competition.compops.events.redis import RedisBackend


async def first_event(feed):
    """The first event of ``feed``, past its idle ticks."""
    async for event in feed:
        if event is not None:
            return event


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
        with override_settings(COMPOPS_ACTIVITY_LENGTH=2):
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
            registered = False
            async for event in events.subscribe(1, idle=0.05):
                if event is None:
                    if registered:
                        return seen
                    registered = True
                else:
                    seen.append(event)

        task = asyncio.ensure_future(consume())
        await asyncio.sleep(0.01)
        await sync_to_async(self.publish_committed)(2, "score-entered", match=5)
        self.assertEqual(await asyncio.wait_for(task, timeout=2), [])

    async def test_subscribe_registers_and_yields_none_immediately(self):
        backend = events.get_backend()

        async def first():
            async for event in events.subscribe(1, idle=5):
                return event, bool(backend._subscribers[1])

        event, registered = await asyncio.wait_for(first(), timeout=1)
        self.assertIsNone(event)
        self.assertTrue(registered)

    async def test_stale_subscriber_is_dropped_without_blocking_others(self):
        backend = events.get_backend()
        closed_loop = asyncio.new_event_loop()
        closed_loop.close()
        stale = (closed_loop, asyncio.Queue())
        backend._subscribers[1].add(stale)

        async def consume():
            async for event in events.subscribe(1, idle=0.5):
                if event is not None:
                    return event

        task = asyncio.ensure_future(consume())
        await asyncio.sleep(0.01)
        await sync_to_async(self.publish_committed)(1, "score-entered", match=5)
        event = await asyncio.wait_for(task, timeout=2)
        self.assertEqual(event["match"], 5)
        self.assertNotIn(stale, backend._subscribers[1])

    def test_publish_failure_after_commit_does_not_raise(self):
        with mock.patch.object(
            events.get_backend(), "publish", side_effect=RuntimeError("boom")
        ):
            with self.captureOnCommitCallbacks(execute=True):
                events.publish(1, "score-entered", match=5)


class RedisBackendTests(TestCase):
    def setUp(self):
        self.server = fakeredis.FakeServer()
        self.backend = RedisBackend(
            "redis://unused",
            sync_client=fakeredis.FakeRedis(server=self.server),
            async_client=fakeredis.FakeAsyncRedis(server=self.server),
        )

    def test_recent_uses_a_bounded_list(self):
        with override_settings(COMPOPS_ACTIVITY_LENGTH=2):
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

    def spy_on_pubsub(self):
        created = []
        original = self.backend.async_client.pubsub

        def spy():
            pubsub = original()
            created.append(pubsub)
            return pubsub

        patcher = mock.patch.object(self.backend.async_client, "pubsub", spy)
        patcher.start()
        self.addCleanup(patcher.stop)
        return created

    async def test_subscribe_yields_none_immediately_once_subscribed(self):
        created = self.spy_on_pubsub()

        async def first():
            async for event in self.backend.subscribe(1, idle=5):
                return event, bool(created[0].subscribed)

        event, subscribed = await asyncio.wait_for(first(), timeout=1)
        self.assertIsNone(event)
        self.assertTrue(subscribed)

    async def test_closing_the_subscription_closes_the_pubsub(self):
        created = self.spy_on_pubsub()

        async with contextlib.aclosing(self.backend.subscribe(1, idle=0.05)) as gen:
            await gen.__anext__()
        (pubsub,) = created
        self.assertFalse(pubsub.subscribed)
        self.assertIsNone(pubsub.connection)

    async def test_pubsub_is_closed_even_if_unsubscribe_fails(self):
        created = self.spy_on_pubsub()

        gen = self.backend.subscribe(1, idle=0.05)
        await gen.__anext__()
        (pubsub,) = created
        with (
            mock.patch.object(
                pubsub, "unsubscribe", side_effect=ConnectionError("gone")
            ),
            mock.patch.object(pubsub, "aclose", wraps=pubsub.aclose) as aclose,
        ):
            with self.assertRaises(ConnectionError):
                await gen.aclose()
        aclose.assert_awaited_once()


class TenantTestsMixin:
    """
    One bus serves every tenant of a django-tenant-schemas site, and season
    ids repeat across tenants, so each season's events stay in the tenant
    whose schema the connection points at.
    """

    def publish_in(self, schema_name, *args, **kwargs):
        # ``publish`` defers to ``transaction.on_commit``, which touches the
        # database connection, so async tests must call it from a thread.
        with schema_context(schema_name), self.captureOnCommitCallbacks(execute=True):
            events.publish(*args, **kwargs)

    def subscribe_in(self, schema_name, season_id):
        # ``subscribe`` reads the schema when it is called, so async tests
        # call it from the thread whose connection they point, as the SSE
        # views do.
        with schema_context(schema_name):
            return events.subscribe(season_id, idle=0.05)

    def recent_in(self, schema_name, season_id):
        with schema_context(schema_name):
            return events.recent(season_id)

    def test_recent_is_kept_per_tenant(self):
        self.publish_in("alpha", 3, "score-entered", actor="priya", summary="alpha")
        self.publish_in("bravo", 3, "score-entered", actor="sam", summary="bravo")
        self.assertEqual([e["summary"] for e in self.recent_in("bravo", 3)], ["bravo"])
        self.assertEqual([e["summary"] for e in self.recent_in("alpha", 3)], ["alpha"])

    async def test_subscriber_receives_its_own_tenants_events_only(self):
        feed = await sync_to_async(self.subscribe_in)("bravo", 3)
        async with contextlib.aclosing(feed):
            await anext(feed)  # registered
            await sync_to_async(self.publish_in)("alpha", 3, "score-entered", match=5)
            await sync_to_async(self.publish_in)("bravo", 3, "score-entered", match=6)
            event = await asyncio.wait_for(first_event(feed), timeout=2)
        self.assertEqual(event["match"], 6)


class MemoryBackendTenantTests(TenantTestsMixin, TestCase):
    def setUp(self):
        events.reset_backend()
        self.addCleanup(events.reset_backend)


class RedisBackendTenantTests(TenantTestsMixin, TestCase):
    def setUp(self):
        server = fakeredis.FakeServer()
        self.redis = fakeredis.FakeRedis(server=server)
        self.enterContext(
            override_settings(
                COMPOPS_EVENTS_BACKEND="tournamentcontrol.competition.compops.events.redis.RedisBackend",
                COMPOPS_EVENTS_OPTIONS={
                    "url": "redis://unused",
                    "sync_client": self.redis,
                    "async_client": fakeredis.FakeAsyncRedis(server=server),
                },
            )
        )
        events.reset_backend()
        self.addCleanup(events.reset_backend)

    def test_single_tenant_ring_is_named_for_the_season(self):
        with self.captureOnCommitCallbacks(execute=True):
            events.publish(3, "score-entered", match=5)
        self.assertEqual(self.redis.keys("compops:*"), [b"compops:season:3:recent"])

    def test_tenant_ring_is_named_for_the_schema_and_the_season(self):
        self.publish_in("alpha", 3, "score-entered", match=5)
        self.assertEqual(
            self.redis.keys("compops:*"), [b"compops:alpha:season:3:recent"]
        )

    async def test_single_tenant_channel_is_named_for_the_season(self):
        async with contextlib.aclosing(events.subscribe(3, idle=0.05)) as feed:
            await anext(feed)  # subscribed
            self.assertEqual(self.redis.pubsub_channels(), [b"compops:season:3"])

    async def test_tenant_channel_is_named_for_the_schema_and_the_season(self):
        feed = await sync_to_async(self.subscribe_in)("alpha", 3)
        async with contextlib.aclosing(feed):
            await anext(feed)  # subscribed
            self.assertEqual(
                self.redis.pubsub_channels(), [b"compops:alpha:season:3"]
            )


class BackendSelectionTests(TestCase):
    def tearDown(self):
        events.reset_backend()

    def test_default_is_memory(self):
        events.reset_backend()
        self.assertIsInstance(events.get_backend(), MemoryBackend)

    @override_settings(
        COMPOPS_EVENTS_BACKEND="tournamentcontrol.competition.compops.events.redis.RedisBackend",
        COMPOPS_EVENTS_OPTIONS={"url": "redis://localhost/0"},
    )
    def test_redis_selected_by_setting(self):
        events.reset_backend()
        self.assertIsInstance(events.get_backend(), RedisBackend)

    @override_settings(
        COMPOPS_EVENTS_BACKEND="tournamentcontrol.competition.compops.events.redis.RedisBackend",
        COMPOPS_EVENTS_OPTIONS={},
    )
    def test_redis_without_url_is_an_error(self):
        events.reset_backend()
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "COMPOPS_EVENTS_OPTIONS do not suit "
            "tournamentcontrol.competition.compops.events.redis.RedisBackend",
        ):
            events.get_backend()

    @override_settings(
        COMPOPS_EVENTS_BACKEND="tournamentcontrol.competition.compops.nope.Backend"
    )
    def test_unknown_backend_is_an_error(self):
        events.reset_backend()
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "COMPOPS_EVENTS_BACKEND 'tournamentcontrol.competition.compops.nope.Backend' "
            "cannot be imported",
        ):
            events.get_backend()
