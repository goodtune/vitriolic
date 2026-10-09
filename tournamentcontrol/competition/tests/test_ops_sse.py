import asyncio
import datetime
from zoneinfo import ZoneInfo

from asgiref.sync import sync_to_async
from asgiref.testing import ApplicationCommunicator
from django.contrib.auth.models import Permission
from django.core.asgi import get_asgi_application
from django.test import TransactionTestCase as DjangoTransactionTestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from test_plus import TestCase
from test_plus.test import BaseTestCase

from tournamentcontrol.competition.ops import events
from tournamentcontrol.competition.tests import factories

TZ = ZoneInfo("Australia/Brisbane")

SNAPSHOT_IDS = (
    "results",
    "scorers",
    "streams",
    "activity",
    "results-count",
    "results-count-tab",
    "scorers-count",
    "scorers-count-tab",
    "streams-count",
    "streams-count-rail",
)

# The last fragment of each kind of push, so a reader knows it has the lot.
LAST_COUNT = 'id="streams-count-rail"'
LAST_ACTIVITY = '<ul id="activity"'


class Reader:
    """
    Read chunks from one streaming response, keeping the same iterator
    between reads so the subscription stays open until ``close``.
    """

    def __init__(self, response):
        self.response = response
        self.stream = response.streaming_content.__aiter__()

    async def until(self, marker, timeout=5):
        """Read chunks until ``marker`` appears in one; return them all."""

        async def consume():
            chunks = []
            while True:
                chunk = (await self.stream.__anext__()).decode()
                chunks.append(chunk)
                if marker in chunk:
                    return chunks

        return await asyncio.wait_for(consume(), timeout)

    async def next(self, timeout=5):
        return (await asyncio.wait_for(self.stream.__anext__(), timeout)).decode()

    async def close(self):
        await self.stream.aclose()


class TransactionTestCase(DjangoTransactionTestCase, BaseTestCase):
    """
    django-test-plus helpers over committed data, for tests that drive the
    ASGI handler: it serves each request on its own thread and database
    connection, which cannot see a ``TestCase``'s uncommitted rows.
    """


class SseFixture:
    def setUp(self):
        events.reset_backend()
        self.addCleanup(events.reset_backend)
        self.staff = factories.UserFactory.create(is_staff=True)
        self.staff.user_permissions.add(Permission.objects.get(codename="change_match"))
        self.user = factories.UserFactory.create()
        self.season = factories.SeasonFactory.create(
            slug="pc26",
            slug_locked=True,
            competition__slug="pacific-cup",
            competition__slug_locked=True,
            timezone="Australia/Brisbane",
        )
        self.stage = factories.StageFactory.create(division__season=self.season)
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, 8), TZ)
        self.match = factories.MatchFactory.create(
            stage=self.stage, datetime=when, date=when.date(), time=when.time()
        )
        self.kw = {
            "competition": "pacific-cup",
            "season": "pc26",
            "datestr": "20261008",
        }
        self.url = reverse("ops:events", kwargs=self.kw)

    def publish_committed(self, *args, **kwargs):
        # ``publish`` defers to ``transaction.on_commit``, which touches the
        # database connection, so async tests must call it from a thread.
        with self.captureOnCommitCallbacks(execute=True):
            events.publish(*args, **kwargs)

    async def publish(self, *args, **kwargs):
        await sync_to_async(self.publish_committed)(*args, **kwargs)

    async def get(self, url=None, user=None):
        await self.async_client.aforce_login(user or self.staff)
        return await self.async_client.get(
            url or self.url, headers={"Datastar-Request": "true"}
        )

    async def connect(self, url=None, user=None):
        """Open the stream and read the snapshot, returning the reader."""
        reader = Reader(await self.get(url, user))
        snapshot = await reader.until(LAST_COUNT)
        return reader, snapshot


@freeze_time("2026-10-08 00:00 +10:00", real_asyncio=True)
class OpsEventsTests(SseFixture, TestCase):
    async def test_anonymous_is_redirected(self):
        response = await self.async_client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/accounts/login/"))

    async def test_non_staff_is_forbidden(self):
        response = await self.get(user=self.user)
        self.assertEqual(response.status_code, 403)

    async def test_unknown_season_is_not_found(self):
        response = await self.get(
            reverse("ops:events", kwargs={**self.kw, "season": "nope"})
        )
        self.assertEqual(response.status_code, 404)

    async def test_bad_date_is_not_found(self):
        response = await self.get(
            reverse("ops:events", kwargs={**self.kw, "datestr": "20261399"})
        )
        self.assertEqual(response.status_code, 404)

    async def test_headers(self):
        response = await self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream; charset=utf-8")
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertEqual(response["X-Accel-Buffering"], "no")
        await response.streaming_content.aclose()

    async def test_snapshot_then_push(self):
        reader, snapshot = await self.connect()
        try:
            self.assertEqual(len(snapshot), len(SNAPSHOT_IDS))
            for chunk, element in zip(snapshot, SNAPSHOT_IDS):
                self.assertIn('id="%s"' % element, chunk)

            await self.publish(
                self.season.pk,
                "score-entered",
                actor="priya",
                summary="x",
                match=self.match.pk,
                adjusted=False,
            )
            pushed = "".join(await reader.until(LAST_ACTIVITY))
            self.assertIn('data: elements <div id="slot-0800"', pushed)
            self.assertIn('data: elements <span id="results-count"', pushed)
            self.assertIn('data: elements <ul id="activity"', pushed)
        finally:
            await reader.close()

    async def test_statistics_entered_pushes_scorers_and_counts(self):
        reader, _ = await self.connect()
        try:
            await self.publish(
                self.season.pk, "statistics-entered", summary="x", match=self.match.pk
            )
            pushed = "".join(await reader.until(LAST_COUNT))
            self.assertIn('data: elements <div id="scorers"', pushed)
            self.assertIn('data: elements <ul id="activity"', pushed)
            self.assertIn('data: elements <span id="scorers-count"', pushed)
        finally:
            await reader.close()

    async def test_stream_change_pushes_the_stream_column(self):
        reader, _ = await self.connect()
        try:
            await self.publish(
                self.season.pk,
                "stream-changed",
                summary="x",
                kind="match",
                id=1,
                status="live",
            )
            pushed = "".join(await reader.until(LAST_COUNT))
            self.assertIn('data: elements <div id="streams"', pushed)
            self.assertIn('data: elements <span id="streams-count"', pushed)
            self.assertIn('data: elements <span id="streams-count-rail"', pushed)
        finally:
            await reader.close()

    async def test_unknown_event_pushes_nothing(self):
        reader, _ = await self.connect()
        try:
            await self.publish(self.season.pk, "mystery", summary="x")
            await self.publish(
                self.season.pk, "stream-changed", summary="x", kind="match", id=1
            )
            pushed = "".join(await reader.until(LAST_COUNT))
            self.assertNotIn('id="slot-0800"', pushed)
            self.assertIn('data: elements <div id="streams"', pushed)
        finally:
            await reader.close()

    @override_settings(OPS_EVENTS_KEEPALIVE=0.05)
    async def test_keepalive_comment_when_idle(self):
        reader, _ = await self.connect()
        try:
            self.assertEqual(await reader.next(), ": ping\n\n")
        finally:
            await reader.close()

    async def test_two_subscribers_both_receive_the_patch(self):
        first, _ = await self.connect()
        second, _ = await self.connect()
        try:
            await self.publish(
                self.season.pk,
                "score-entered",
                summary="x",
                match=self.match.pk,
                adjusted=False,
            )
            for reader in (first, second):
                pushed = "".join(await reader.until(LAST_ACTIVITY))
                self.assertIn('id="slot-0800"', pushed)
        finally:
            await first.close()
            await second.close()

    async def test_empty_season_snapshot_renders_every_fragment(self):
        await sync_to_async(factories.SeasonFactory.create)(
            slug="empty",
            slug_locked=True,
            competition__slug="pacific-cup",
            competition__slug_locked=True,
            timezone="Australia/Brisbane",
        )
        reader, snapshot = await self.connect(
            reverse("ops:events", kwargs={**self.kw, "season": "empty"})
        )
        try:
            snapshot = "".join(snapshot)
            self.assertIn(
                '<p id="results-empty" class="empty">No matches on this day.</p>',
                snapshot,
            )
            self.assertIn(
                '<p id="streams-empty" class="empty">'
                "No streamed grounds in this season.</p>",
                snapshot,
            )
        finally:
            await reader.close()


@freeze_time("2026-10-08 00:00 +10:00", real_asyncio=True)
class OpsEventsDisconnectTests(SseFixture, TransactionTestCase):
    async def test_disconnect_unsubscribes(self):
        await self.async_client.aforce_login(self.staff)
        cookie = "sessionid=%s" % self.async_client.cookies["sessionid"].value
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": self.url,
            "raw_path": self.url.encode(),
            "query_string": b"",
            "headers": [
                (b"cookie", cookie.encode()),
                (b"datastar-request", b"true"),
                (b"host", b"testserver"),
            ],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        }
        communicator = ApplicationCommunicator(get_asgi_application(), scope)
        await communicator.send_input({"type": "http.request"})
        start = await communicator.receive_output(5)
        self.assertEqual(start["status"], 200)
        await communicator.receive_output(5)  # first body chunk
        backend = events.get_backend()
        self.assertEqual(len(backend._subscribers[self.season.pk]), 1)
        await communicator.send_input({"type": "http.disconnect"})
        await communicator.wait(5)
        self.assertEqual(len(backend._subscribers[self.season.pk]), 0)
