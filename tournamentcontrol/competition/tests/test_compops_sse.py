import asyncio
import datetime
import json
from unittest import mock
from zoneinfo import ZoneInfo

from asgiref.sync import sync_to_async
from asgiref.testing import ApplicationCommunicator
from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.asgi import get_asgi_application
from django.shortcuts import resolve_url
from django.test import TransactionTestCase as DjangoTransactionTestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from guardian.shortcuts import assign_perm
from test_plus import TestCase
from test_plus.test import BaseTestCase

from touchtechnology.admin.tests.tenancy import schema_context
from tournamentcontrol.competition.compops import events, streams
from tournamentcontrol.competition.compops.sites import CompOpsSite
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_compops_results import HELD

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
        self.url = reverse("compops:events", kwargs=self.kw)
        # The stream validates its connections around each render. Inside a
        # test's wrapping transaction that would close the test connection, so
        # the real thing is replaced here and asserted on where it matters.
        patcher = mock.patch(
            "tournamentcontrol.competition.compops.sse.close_old_connections"
        )
        self.close_old_connections = patcher.start()
        self.addCleanup(patcher.stop)

    def publish_committed(self, *args, **kwargs):
        # ``publish`` defers to ``transaction.on_commit``, which touches the
        # database connection, so async tests must call it from a thread.
        with self.captureOnCommitCallbacks(execute=True):
            events.publish(*args, **kwargs)

    async def publish(self, *args, **kwargs):
        await sync_to_async(self.publish_committed)(*args, **kwargs)

    async def publish_change(self, obj, status):
        """Publish ``obj``'s broadcast change as the site does after a transition."""

        def publish():
            with self.captureOnCommitCallbacks(execute=True):
                streams.publish_change(obj, status, actor="op")

        await sync_to_async(publish)()

    async def publish_in(self, schema_name, *args, **kwargs):
        """Publish as a request in the tenant ``schema_name`` does."""

        def publish():
            with schema_context(schema_name):
                self.publish_committed(*args, **kwargs)

        await sync_to_async(publish)()

    async def point_at(self, schema_name):
        """
        Point the requests of the rest of the test at the tenant
        ``schema_name``. Their sync code runs on the test's thread, so that
        thread's connection is the one to point; the event loop has a
        connection of its own, as it does under an ASGI server.
        """

        def enter():
            self.enterContext(schema_context(schema_name))

        await sync_to_async(enter)()

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

    @staticmethod
    def held(block):
        return f'data: elements <div id="{block}" class="stream" {HELD}>'

    @staticmethod
    def released(block):
        return f'data: elements <div id="{block}" class="stream">'


@freeze_time("2026-10-08 00:00 +10:00", real_asyncio=True)
class CompOpsEventsTests(SseFixture, TestCase):
    def setUp(self):
        super().setUp()
        venue = factories.VenueFactory.create(season=self.season)
        self.ground = factories.GroundFactory.create(
            venue=venue, title="Field 1", live_stream=True
        )
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, 10, 40), TZ)
        self.streamed = factories.MatchFactory.create(
            stage=self.stage,
            datetime=when,
            date=when.date(),
            time=when.time(),
            play_at=self.ground,
            live_stream=True,
            external_identifier="yt-1",
        )

    async def test_anonymous_is_redirected(self):
        response = await self.async_client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response["Location"].startswith(str(resolve_url(settings.LOGIN_URL)))
        )

    async def test_non_staff_is_forbidden(self):
        response = await self.get(user=self.user)
        self.assertEqual(response.status_code, 403)

    async def test_unknown_season_is_not_found(self):
        response = await self.get(
            reverse("compops:events", kwargs={**self.kw, "season": "nope"})
        )
        self.assertEqual(response.status_code, 404)

    async def test_bad_date_is_not_found(self):
        response = await self.get(
            reverse("compops:events", kwargs={**self.kw, "datestr": "20261399"})
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
                self.assertIn(f'id="{element}"', chunk)

            await self.publish(
                self.season.pk,
                "score-entered",
                actor="priya",
                summary="x",
                match=self.match.pk,
                adjusted=False,
            )
            pushed = "".join(await reader.until(LAST_ACTIVITY))
            # The row the event is about is not held: the push updates it.
            self.assertIn(
                f'data: elements <div id="match-{self.match.pk}" class="row">',
                pushed.splitlines(),
            )
            self.assertIn('data: elements <div id="slot-0800-h"', pushed)
            self.assertNotIn('data: elements <div id="slot-0800" class="slot"', pushed)
            self.assertIn('data: elements <span id="results-count"', pushed)
            self.assertIn('data: elements <ul id="activity"', pushed)
        finally:
            await reader.close()

    async def test_the_snapshot_passes_over_the_rows_a_person_holds(self):
        # Datastar's morph leaves a row alone only when the page's row and the
        # snapshot's both carry data-ignore-morph, so the snapshot marks every
        # row and the page marks the rows the person holds.
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, 9), TZ)
        done = await sync_to_async(factories.MatchFactory.create)(
            stage=self.stage,
            datetime=when,
            date=when.date(),
            time=when.time(),
            home_team_score=3,
            away_team_score=1,
        )
        reader, snapshot = await self.connect()
        try:
            rows = snapshot[0].splitlines()
            for match in (self.match, done):
                self.assertIn(
                    f'data: elements <div id="match-{match.pk}" class="row" '
                    'data-ignore-morph data-preserve-attr="data-ignore-morph">',
                    rows,
                )
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
            await self.publish_change(self.streamed, "live")
            pushed = "".join(await reader.until(LAST_COUNT))
            self.assertIn(
                self.released(f"stream-{self.ground.pk}"), pushed.splitlines()
            )
            self.assertIn('data: elements <div id="streams"', pushed)
            self.assertIn('data: elements <span id="streams-count"', pushed)
            self.assertIn('data: elements <span id="streams-count-rail"', pushed)
        finally:
            await reader.close()

    async def test_unknown_event_pushes_nothing(self):
        reader, _ = await self.connect()
        try:
            await self.publish(self.season.pk, "mystery", summary="x")
            await self.publish_change(self.streamed, "live")
            pushed = "".join(await reader.until(LAST_COUNT))
            self.assertNotIn('id="slot-0800-h"', pushed)
            self.assertIn(
                self.released(f"stream-{self.ground.pk}"), pushed.splitlines()
            )
        finally:
            await reader.close()

    async def test_failed_push_is_logged_and_the_stream_survives(self):
        original = CompOpsSite.event_fragments
        outcomes = [RuntimeError("boom")]

        def flaky(site, *args, **kwargs):
            # The stream only renders while a reader pulls from it, so the
            # first push fails and every later one is the real thing.
            if outcomes:
                raise outcomes.pop()
            return original(site, *args, **kwargs)

        reader, _ = await self.connect()
        try:
            with mock.patch.object(
                CompOpsSite, "event_fragments", autospec=True, side_effect=flaky
            ) as patched:
                await self.publish(
                    self.season.pk, "score-entered", summary="x", match=self.match.pk
                )
                await self.publish_change(self.streamed, "live")
                with self.assertLogs(
                    "tournamentcontrol.competition.compops.sse", level="ERROR"
                ):
                    pushed = "".join(await reader.until(LAST_COUNT))
            self.assertEqual(patched.call_count, 2)
            self.assertIn(
                self.released(f"stream-{self.ground.pk}"), pushed.splitlines()
            )
            self.assertNotIn('id="slot-0800-h"', pushed)
        finally:
            await reader.close()

    async def test_another_tenants_events_are_not_pushed(self):
        await self.point_at("alpha")
        reader, _ = await self.connect()
        try:
            await self.publish_in(
                "bravo",
                self.season.pk,
                "stream-changed",
                kind="match",
                id=self.streamed.pk,
                ground=self.ground.pk,
            )
            await self.publish_in(
                "alpha", self.season.pk, "statistics-entered", match=self.match.pk
            )
            pushed = await reader.until(LAST_COUNT)
            self.assertIn('data: elements <div id="scorers"', pushed[0])
        finally:
            await reader.close()

    async def test_connections_are_validated_around_a_push(self):
        reader, _ = await self.connect()
        try:
            before = self.close_old_connections.call_count
            await self.publish_change(self.streamed, "live")
            await reader.until(LAST_COUNT)
            self.assertGreaterEqual(self.close_old_connections.call_count - before, 2)
        finally:
            await reader.close()

    @override_settings(COMPOPS_EVENTS_KEEPALIVE=0.05)
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
                self.assertIn(f'id="match-{self.match.pk}"', pushed)
                self.assertIn('id="slot-0800-h"', pushed)
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
            reverse("compops:events", kwargs={**self.kw, "season": "empty"})
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
class HeldStreamsEventsTests(SseFixture, TestCase):
    """
    The day page's stream and the blocks of its streams column (see
    ground_stream in day.html): the snapshot marks every block, so the blocks
    the page holds pass over it, and a push marks every block but the one it
    is about, which it releases.
    """

    def setUp(self):
        super().setUp()
        venue = factories.VenueFactory.create(season=self.season)
        self.field1 = factories.GroundFactory.create(
            venue=venue, title="Field 1", live_stream=True
        )
        self.field2 = factories.GroundFactory.create(
            venue=venue, title="Field 2", live_stream=True
        )
        self.on_field1 = self.streamed(self.field1, "yt-1")
        self.on_field2 = self.streamed(self.field2, "yt-2")
        self.event = factories.LiveStreamEventFactory.create(
            season=self.season,
            start=timezone.make_aware(datetime.datetime(2026, 10, 8, 17, 30), TZ),
        )
        self.blocks = (
            f"stream-{self.field1.pk}",
            f"stream-{self.field2.pk}",
            f"event-{self.event.pk}",
        )

    def streamed(self, ground, identifier):
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, 10, 40), TZ)
        return factories.MatchFactory.create(
            stage=self.stage,
            datetime=when,
            date=when.date(),
            time=when.time(),
            play_at=ground,
            live_stream=True,
            external_identifier=identifier,
        )


    async def test_the_snapshot_marks_every_block(self):
        reader, snapshot = await self.connect()
        try:
            lines = snapshot[SNAPSHOT_IDS.index("streams")].splitlines()
            for block in self.blocks:
                self.assertIn(self.held(block), lines)
        finally:
            await reader.close()

    async def test_a_push_about_a_match_releases_its_grounds_block_and_holds_the_rest(
        self,
    ):
        reader, _ = await self.connect()
        try:
            await self.publish_change(self.on_field1, "live")
            lines = "".join(await reader.until(LAST_COUNT)).splitlines()
            self.assertIn(self.released(f"stream-{self.field1.pk}"), lines)
            self.assertIn(self.held(f"stream-{self.field2.pk}"), lines)
            self.assertIn(self.held(f"event-{self.event.pk}"), lines)
        finally:
            await reader.close()

    async def test_a_push_about_a_season_event_releases_it_and_holds_the_grounds(
        self,
    ):
        reader, _ = await self.connect()
        try:
            await self.publish_change(self.event, "testing")
            lines = "".join(await reader.until(LAST_COUNT)).splitlines()
            self.assertIn(self.released(f"event-{self.event.pk}"), lines)
            self.assertIn(self.held(f"stream-{self.field1.pk}"), lines)
            self.assertIn(self.held(f"stream-{self.field2.pk}"), lines)
        finally:
            await reader.close()


@freeze_time("2026-10-08 00:00 +10:00", real_asyncio=True)
class CompOpsEventsDisconnectTests(SseFixture, TransactionTestCase):
    async def test_disconnect_unsubscribes(self):
        await self.async_client.aforce_login(self.staff)
        cookie = f"sessionid={self.async_client.cookies['sessionid'].value}"
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
        self.assertEqual(len(backend._subscribers[f"season:{self.season.pk}"]), 1)
        await communicator.send_input({"type": "http.disconnect"})
        await communicator.wait(5)
        self.assertEqual(len(backend._subscribers[f"season:{self.season.pk}"]), 0)


@freeze_time("2026-10-08 10:50 +10:00", real_asyncio=True)
class BoothEventsTests(SseFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.commentator = factories.UserFactory.create()
        assign_perm("competition.stream_season", self.commentator, self.season)
        venue = factories.VenueFactory.create(season=self.season)
        self.field1 = factories.GroundFactory.create(
            venue=venue, title="Field 1", slug="field-1", live_stream=True
        )
        self.field2 = factories.GroundFactory.create(
            venue=venue, title="Field 2", slug="field-2", live_stream=False
        )
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, 10, 40), TZ)
        self.current = factories.MatchFactory.create(
            stage=self.stage,
            datetime=when,
            date=when.date(),
            time=when.time(),
            play_at=self.field1,
            live_stream=True,
            external_identifier="yt",
            live_stream_status="live",
        )
        self.booth_kw = {
            "competition": "pacific-cup",
            "season": "pc26",
            "ground": "field-1",
        }
        self.booth_url = reverse("compops:booth-events", kwargs=self.booth_kw)

    async def connect_booth(self, signals=None, url=None, until='<div id="pane"'):
        """Open the booth stream as the commentator and read the snapshot."""
        await self.async_client.aforce_login(self.commentator)
        query = {"datastar": json.dumps(signals)} if signals else {}
        response = await self.async_client.get(
            url or self.booth_url, query, headers={"Datastar-Request": "true"}
        )
        reader = Reader(response)
        return reader, await reader.until(until)

    async def test_anonymous_is_redirected(self):
        response = await self.async_client.get(self.booth_url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response["Location"].startswith(str(resolve_url(settings.LOGIN_URL)))
        )

    async def test_outsider_is_forbidden(self):
        response = await self.get(self.booth_url, user=self.user)
        self.assertEqual(response.status_code, 403)

    async def test_staff_without_stream_permission_is_forbidden(self):
        response = await self.get(self.booth_url, user=self.staff)
        self.assertEqual(response.status_code, 403)

    async def test_unknown_season_is_not_found(self):
        response = await self.get(
            reverse("compops:booth-events", kwargs={**self.booth_kw, "season": "nope"})
        )
        self.assertEqual(response.status_code, 404)

    async def test_unstreamed_ground_is_not_found(self):
        await self.async_client.aforce_login(self.commentator)
        for ground in ("field-2", "nowhere"):
            response = await self.async_client.get(
                reverse(
                    "compops:booth-events", kwargs={**self.booth_kw, "ground": ground}
                ),
                headers={"Datastar-Request": "true"},
            )
            self.assertEqual(response.status_code, 404)

    async def test_headers(self):
        await self.async_client.aforce_login(self.commentator)
        response = await self.async_client.get(
            self.booth_url, headers={"Datastar-Request": "true"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream; charset=utf-8")
        self.assertEqual(response["Cache-Control"], "no-cache")
        await response.streaming_content.aclose()

    async def test_snapshot_has_onair_strip_and_pane(self):
        reader, chunks = await self.connect_booth(
            {"pane": "sheets", "match": self.current.pk}
        )
        try:
            self.assertEqual(len(chunks), 3)
            snapshot = "".join(chunks)
            self.assertIn('<section id="onair"', chunks[0])
            self.assertIn('<section id="strip"', chunks[1])
            self.assertIn('<div id="pane" class="pane sheets">', snapshot)
        finally:
            await reader.close()

    async def test_snapshot_without_signals_is_lamp_and_strip(self):
        reader, chunks = await self.connect_booth(until='<section id="strip"')
        try:
            self.assertEqual(len(chunks), 2)
            self.assertIn('<section id="onair"', chunks[0])
        finally:
            await reader.close()

    async def test_snapshot_ignores_a_match_that_is_not_on_this_ground(self):
        other = await sync_to_async(factories.MatchFactory.create)(stage=self.stage)
        reader, chunks = await self.connect_booth(
            {"pane": "sheets", "match": other.pk}, until='<section id="strip"'
        )
        try:
            self.assertEqual(len(chunks), 2)
            await self.publish(
                self.season.pk, "statistics-entered", summary="x", match=other.pk
            )
            await self.publish_change(self.current, "live")
            pushed = await reader.until('<section id="strip"')
            self.assertEqual(len(pushed), 2)
            self.assertNotIn('id="pane"', "".join(pushed))
        finally:
            await reader.close()

    async def test_snapshot_tolerates_a_malformed_match_signal(self):
        reader, chunks = await self.connect_booth(
            {"pane": "sheets", "match": "abc"}, until='<section id="strip"'
        )
        try:
            self.assertEqual(len(chunks), 2)
        finally:
            await reader.close()

    async def test_runsheet_snapshot(self):
        reader, chunks = await self.connect_booth({"pane": "runsheet", "match": None})
        try:
            self.assertIn('<div id="pane" class="pane runsheet">', "".join(chunks))
        finally:
            await reader.close()

    async def test_the_snapshot_marks_the_lamp(self):
        # A lamp that shows a refusal is held (see lamp in booth.html), so the
        # snapshot marks the lamp and the page's held lamp passes over it.
        reader, chunks = await self.connect_booth(until='<section id="strip"')
        try:
            self.assertIn(
                f'data: elements <section id="onair" class="onair" {HELD}>',
                chunks[0].splitlines(),
            )
        finally:
            await reader.close()

    async def test_a_push_about_this_ground_releases_the_lamp(self):
        reader, _ = await self.connect_booth(until='<section id="strip"')
        try:
            await self.publish_change(self.current, "complete")
            pushed = await reader.until('<section id="strip"')
            self.assertIn(
                'data: elements <section id="onair" class="onair">',
                pushed[0].splitlines(),
            )
        finally:
            await reader.close()

    async def test_a_push_about_another_ground_holds_the_lamp(self):
        field3 = await sync_to_async(factories.GroundFactory.create)(
            venue=self.field1.venue, title="Field 3", slug="field-3", live_stream=True
        )
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, 10, 40), TZ)
        elsewhere = await sync_to_async(factories.MatchFactory.create)(
            stage=self.stage,
            datetime=when,
            date=when.date(),
            time=when.time(),
            play_at=field3,
            live_stream=True,
            external_identifier="yt-3",
        )
        reader, _ = await self.connect_booth(until='<section id="strip"')
        try:
            await self.publish_change(elsewhere, "live")
            pushed = await reader.until('<section id="strip"')
            self.assertIn(
                f'data: elements <section id="onair" class="onair" {HELD}>',
                pushed[0].splitlines(),
            )
        finally:
            await reader.close()

    async def test_stream_change_pushes_the_lamp_and_strip(self):
        reader, _ = await self.connect_booth(
            {"pane": "sheets", "match": self.current.pk}
        )
        try:
            await self.publish(
                self.season.pk,
                "stream-changed",
                summary="x",
                kind="match",
                id=self.current.pk,
                status="complete",
            )
            # The team sheets are not touched by a stream change, so the
            # statistics push that follows is the next to carry the pane.
            await self.publish(
                self.season.pk, "statistics-entered", summary="x", match=self.current.pk
            )
            pushed = await reader.until('<div id="pane"')
            self.assertEqual(len(pushed), 3)
            self.assertIn('<section id="onair"', pushed[0])
            self.assertIn('<section id="strip"', pushed[1])
            self.assertIn('<div id="pane" class="pane sheets">', pushed[2])
        finally:
            await reader.close()

    async def test_stream_change_refreshes_the_open_runsheet(self):
        reader, _ = await self.connect_booth({"pane": "runsheet", "match": None})
        try:
            await self.publish_change(self.current, "live")
            pushed = await reader.until('<div id="pane"')
            self.assertEqual(len(pushed), 3)
            self.assertIn('<div id="pane" class="pane runsheet">', pushed[2])
        finally:
            await reader.close()

    async def test_score_pushes_results_pane_but_not_sheets(self):
        sheets, _ = await self.connect_booth(
            {"pane": "sheets", "match": self.current.pk}
        )
        results, _ = await self.connect_booth(
            {"pane": "results", "match": self.current.pk}
        )
        try:
            await self.publish(
                self.season.pk,
                "score-entered",
                summary="x",
                match=self.current.pk,
                adjusted=False,
            )
            pushed = await results.until('<div id="pane"')
            self.assertEqual(len(pushed), 2)
            self.assertIn('<section id="strip"', pushed[0])
            self.assertIn('<div id="pane" class="pane results">', pushed[1])

            # The sheets stream saw the strip alone, so the pane it finally
            # receives comes from the statistics push.
            await self.publish(
                self.season.pk, "statistics-entered", summary="x", match=self.current.pk
            )
            pushed = await sheets.until('<div id="pane"')
            self.assertEqual(len(pushed), 2)
            self.assertIn('<section id="strip"', pushed[0])
            self.assertIn('<div id="pane" class="pane sheets">', pushed[1])
        finally:
            await results.close()
            await sheets.close()

    async def test_bye_pushes_the_ladder_pane(self):
        reader, _ = await self.connect_booth(
            {"pane": "ladder", "match": self.current.pk}
        )
        try:
            await self.publish(
                self.season.pk, "bye-processed", summary="x", match=self.current.pk
            )
            pushed = await reader.until('<div id="pane"')
            self.assertEqual(len(pushed), 2)
            self.assertIn('<div id="pane" class="pane ladder">', pushed[1])
        finally:
            await reader.close()

    async def test_statistics_push_the_leaders_pane(self):
        reader, _ = await self.connect_booth(
            {"pane": "leaders", "match": self.current.pk}
        )
        try:
            await self.publish(
                self.season.pk, "statistics-entered", summary="x", match=self.current.pk
            )
            pushed = await reader.until('<div id="pane"')
            self.assertEqual(len(pushed), 1)
            self.assertIn('<div id="pane" class="pane leaders">', pushed[0])
        finally:
            await reader.close()

    async def test_another_tenants_events_are_not_pushed(self):
        await self.point_at("alpha")
        reader, _ = await self.connect_booth(
            {"pane": "sheets", "match": self.current.pk}
        )
        try:
            await self.publish_in(
                "bravo",
                self.season.pk,
                "stream-changed",
                kind="match",
                id=self.current.pk,
                status="complete",
            )
            await self.publish_in(
                "alpha", self.season.pk, "statistics-entered", match=self.current.pk
            )
            pushed = await reader.until('<div id="pane"')
            self.assertEqual(len(pushed), 1)
            self.assertIn('<div id="pane" class="pane sheets">', pushed[0])
        finally:
            await reader.close()

    async def test_unknown_event_pushes_nothing(self):
        reader, _ = await self.connect_booth(
            {"pane": "sheets", "match": self.current.pk}
        )
        try:
            await self.publish(self.season.pk, "mystery", summary="x")
            await self.publish_change(self.current, "live")
            pushed = await reader.until('<section id="strip"')
            self.assertEqual(len(pushed), 2)
            self.assertIn('<section id="onair"', pushed[0])
        finally:
            await reader.close()
