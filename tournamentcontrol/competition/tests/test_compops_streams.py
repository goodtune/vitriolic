import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Permission
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from freezegun import freeze_time
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from test_plus import TestCase

from tournamentcontrol.competition.compops import events, streams
from tournamentcontrol.competition.models import LiveStreamEvent, Match
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_compops_results import (
    DATASTAR,
    HELD,
    element_patches,
)
from tournamentcontrol.competition.tests.test_live_stream_transition import (
    YOUTUBE_SEASON,
    youtube_mock,
)

TZ = ZoneInfo("Australia/Brisbane")


@freeze_time("2026-10-08 10:50 +10:00")
class StreamsFixture(TestCase):
    def setUp(self):
        super().setUp()
        events.reset_backend()
        self.streamer = factories.UserFactory.create(is_staff=True)
        self.streamer.user_permissions.add(
            Permission.objects.get(codename="stream_season")
        )
        self.staff = factories.UserFactory.create(is_staff=True)
        self.season = factories.SeasonFactory.create(
            slug="pc26",
            slug_locked=True,
            competition__slug="pacific-cup",
            competition__slug_locked=True,
            timezone="Australia/Brisbane",
            **YOUTUBE_SEASON,
        )
        venue = factories.VenueFactory.create(season=self.season)
        self.field1 = factories.GroundFactory.create(
            venue=venue, title="Field 1", live_stream=True
        )
        stage = factories.StageFactory.create(division__season=self.season)
        self.current = self.make(
            stage,
            10,
            40,
            live_stream=True,
            external_identifier="yt-current",
            live_stream_status="testing",
        )
        self.following = self.make(
            stage, 11, 20, live_stream=True, external_identifier="yt-next"
        )
        self.event = factories.LiveStreamEventFactory.create(
            season=self.season,
            start=timezone.make_aware(datetime.datetime(2026, 10, 8, 17, 30), TZ),
        )
        self.kw = {
            "competition": "pacific-cup",
            "season": "pc26",
            "datestr": "20261008",
        }

    def make(self, stage, hour, minute, play_at=None, **kwargs):
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, hour, minute), TZ)
        return factories.MatchFactory.create(
            stage=stage,
            datetime=when,
            date=when.date(),
            time=when.time(),
            play_at=play_at or self.field1,
            **kwargs,
        )

    def url(self, name, **extra):
        return reverse(f"compops:{name}", kwargs={**self.kw, **extra})

    def send(self, name, method="post", datastar=False, **extra):
        """Request a CompOps view; a Datastar request returns the streamed body."""
        getattr(self, method)(
            f"compops:{name}", extra=DATASTAR if datastar else {}, **self.kw, **extra
        )
        if datastar:
            return b"".join(self.last_response.streaming_content).decode()


class StreamsFragmentTests(StreamsFixture):
    def test_current_match_with_status_and_buttons(self):
        with self.login(self.streamer):
            self.get("compops:streams", **self.kw)
        self.assertResponseContains('<span class="badge testing">testing</span>')
        self.assertResponseContains(
            '<button class="btn g sm" type="submit">Go live</button>'
        )

    def test_live_starting_counts_as_live(self):
        self.current.live_stream_status = "liveStarting"
        self.current.save()
        with self.login(self.streamer):
            self.get("compops:day", **self.kw)
        self.assertResponseContains('<span id="streams-count" class="count">1</span>')
        self.assertResponseContains(
            '<button class="btn r sm" type="submit">End</button>'
        )

    def test_whole_slot_actions_follow_the_clock(self):
        with self.login(self.streamer):
            self.get("compops:streams", **self.kw)
        for label in (
            "Go live: all 10:40",
            "End: all 10:40",
            "Test: all 11:20",
            "Go live: all 11:20",
        ):
            self.assertResponseContains(
                f'<button class="btn sm" type="submit">{label}</button>'
            )
        body = self.last_response.content.decode()
        for key, status in (
            ("1040", "live"),
            ("1040", "complete"),
            ("1120", "testing"),
            ("1120", "live"),
        ):
            self.assertIn(
                f'action="{self.url("slot-stream", slot_key=key, status=status)}"',
                body,
            )

    def test_whole_slot_actions_ignore_unentered_results(self):
        # An earlier slot still waiting on results is not the slot on air.
        self.make(self.current.stage, 9, 20, live_stream=True)
        with self.login(self.streamer):
            self.get("compops:streams", **self.kw)
        self.assertResponseContains(
            '<button class="btn sm" type="submit">Go live: all 10:40</button>'
        )
        self.assertResponseNotContains(
            '<button class="btn sm" type="submit">Go live: all 09:20</button>'
        )

    def test_next_match_has_its_own_buttons(self):
        with self.login(self.streamer):
            self.get("compops:streams", **self.kw)
        self.assertResponseContains(
            '<button class="btn sm" type="submit">Test</button>'
        )
        url = self.url("match-stream", match_pk=self.following.pk, status="testing")
        self.assertIn(f'action="{url}"', self.last_response.content.decode())

    def test_without_permission_no_buttons(self):
        with self.login(self.staff):
            self.get("compops:streams", **self.kw)
        self.assert_http_200_ok()
        self.assertResponseContains('<span class="badge testing">testing</span>')
        self.assertResponseNotContains(
            '<button class="btn g sm" type="submit">Go live</button>'
        )
        self.assertResponseNotContains(
            '<button class="btn sm" type="submit">Go live: all 10:40</button>'
        )

    def test_next_match_and_season_event_listed(self):
        with self.login(self.streamer):
            self.get("compops:streams", **self.kw)
        self.assertResponseContains('<span class="badge none">no status</span>')
        self.assertResponseContains(f'<div class="match">{self.event.title}</div>')

    def test_event_time_is_shown_in_the_season_timezone(self):
        with self.login(self.streamer):
            self.get("compops:streams", **self.kw)
        self.assertResponseContains('<div class="ground">17:30</div>')


class MatchTransitionTests(StreamsFixture):
    @mock.patch("tournamentcontrol.competition.models.build")
    def test_go_live_stores_status_and_publishes(self, build):
        build.return_value = youtube_mock("testing")
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            body = self.send(
                "match-stream", datastar=True, match_pk=self.current.pk, status="live"
            )
        self.assert_http_200_ok()
        self.assertIn('<span class="badge live">live</span>', body)
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "live")
        (event,) = events.recent(self.season.pk)
        self.assertEqual(event["type"], "stream-changed")
        self.assertEqual(event["status"], "live")
        self.assertEqual(
            event["summary"],
            f"Field 1 · {self.current.home_team.title} v "
            f"{self.current.away_team.title} → live",
        )

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_plain_post_redirects(self, build):
        build.return_value = youtube_mock("testing")
        with self.login(self.streamer):
            self.send("match-stream", match_pk=self.current.pk, status="live")
        self.assert_http_302_found(url=self.url("day"))

    def test_without_permission_is_403(self):
        with self.login(self.staff):
            self.send("match-stream", match_pk=self.current.pk, status="live")
        self.assert_http_403_forbidden()

    def test_unknown_status_is_404(self):
        with self.login(self.streamer):
            self.send("match-stream", match_pk=self.current.pk, status="paused")
        self.assert_http_404_not_found()

    def test_get_is_not_allowed(self):
        with self.login(self.streamer):
            self.send(
                "match-stream", method="get", match_pk=self.current.pk, status="live"
            )
        self.assert_http_405_method_not_allowed()

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_missing_broadcast_reports_an_error_and_publishes_nothing(self, build):
        build.return_value = youtube_mock()
        orphan = self.make(self.current.stage, 12, 0, live_stream=True)
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            body = self.send(
                "match-stream", datastar=True, match_pk=orphan.pk, status="live"
            )
        self.assert_http_200_ok()
        message = f"{streams.describe(orphan)}: {orphan} does not have a live stream identifier"
        self.assertIn(f'<p class="warn">{escape(message)}</p>', body)
        self.assertEqual(events.recent(self.season.pk), [])

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_match_not_streamed_is_404_and_not_sent(self, build):
        build.return_value = youtube_mock("ready")
        # A stale identifier outlives the opt-in until the broadcast is gone.
        turned_off = self.make(
            self.current.stage,
            12,
            0,
            external_identifier="yt-off",
            live_stream_status="ready",
        )
        with self.login(self.streamer):
            self.send("match-stream", match_pk=turned_off.pk, status="live")
        self.assert_http_404_not_found()
        self.assertEqual(build.call_count, 0)
        turned_off.refresh_from_db()
        self.assertEqual(turned_off.live_stream_status, "ready")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_match_on_a_ground_not_streamed_is_404_and_not_sent(self, build):
        build.return_value = youtube_mock("ready")
        field2 = factories.GroundFactory.create(venue=self.field1.venue)
        elsewhere = self.make(
            self.current.stage,
            12,
            0,
            play_at=field2,
            live_stream=True,
            external_identifier="yt-field-2",
            live_stream_status="ready",
        )
        with self.login(self.streamer):
            self.send("match-stream", match_pk=elsewhere.pk, status="live")
        self.assert_http_404_not_found()
        self.assertEqual(build.call_count, 0)
        elsewhere.refresh_from_db()
        self.assertEqual(elsewhere.live_stream_status, "ready")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_expired_credentials_report_an_error_and_publish_nothing(self, build):
        build.side_effect = RefreshError("expired")
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            with self.assertLogs("tournamentcontrol.competition.compops.streams"):
                body = self.send(
                    "match-stream",
                    datastar=True,
                    match_pk=self.current.pk,
                    status="live",
                )
        self.assert_http_200_ok()
        message = f"{streams.describe(self.current)}: expired"
        self.assertIn(f'<p class="warn">{escape(message)}</p>', body)
        self.assertEqual(events.recent(self.season.pk), [])

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_youtube_api_error_reports_the_reason_and_publishes_nothing(self, build):
        service = youtube_mock("testing")
        service.liveBroadcasts.return_value.transition.return_value.execute.side_effect = HttpError(
            resp=mock.Mock(status=403, reason="quota"), content=b"quota"
        )
        build.return_value = service
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            with self.assertLogs("tournamentcontrol.competition.compops.streams"):
                body = self.send(
                    "match-stream",
                    datastar=True,
                    match_pk=self.current.pk,
                    status="live",
                )
        self.assert_http_200_ok()
        message = f"{streams.describe(self.current)}: quota"
        self.assertIn(f'<p class="warn">{escape(message)}</p>', body)
        self.assertEqual(events.recent(self.season.pk), [])


class HeldStreamTests(StreamsFixture):
    """
    A block of the streams column that shows why an action was refused is
    held: a re-render of the whole column (the event stream's snapshot, the
    layout toggle, a push about another stream) leaves it as it is. A refused
    block is sent alone and whole, in replace mode; an action that goes
    through sends the column with no block held.
    """

    def refusing(self, reason):
        """A YouTube service that refuses every transition with ``reason``."""
        service = youtube_mock("testing")
        service.liveBroadcasts.return_value.transition.return_value.execute.side_effect = HttpError(
            resp=mock.Mock(status=403, reason=reason), content=b""
        )
        return service

    def openings(self):
        """The patches of the last response as (mode, opening tag)."""
        return [
            (mode, html.splitlines()[0])
            for mode, html in element_patches(self.last_response)
        ]

    def column(self):
        """The mode and the html of the patch to the streams column."""
        (patch,) = (
            (mode, html)
            for mode, html in element_patches(self.last_response)
            if html.startswith('<div id="streams"')
        )
        return patch

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_a_refused_action_holds_its_ground_with_the_reason(self, build):
        build.return_value = self.refusing("quota")
        with (
            self.login(self.streamer),
            self.assertLogs("tournamentcontrol.competition.compops.streams"),
        ):
            self.post(
                "compops:match-stream",
                match_pk=self.current.pk,
                status="live",
                extra=DATASTAR,
                **self.kw,
            )
        self.assert_http_200_ok()
        ((mode, html),) = element_patches(self.last_response)
        self.assertEqual(mode, "replace")
        self.assertEqual(
            html.splitlines()[0],
            f'<div id="stream-{self.field1.pk}" class="stream" {HELD}>',
        )
        message = f"{streams.describe(self.current)}: quota"
        self.assertInHTML(f'<p class="warn">{escape(message)}</p>', html, count=1)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_a_refused_whole_slot_holds_each_ground_refused(self, build):
        build.return_value = self.refusing("quota")
        field2 = factories.GroundFactory.create(
            venue=self.field1.venue, title="Field 2", live_stream=True
        )
        self.make(
            self.current.stage,
            10,
            40,
            play_at=field2,
            live_stream=True,
            external_identifier="yt-field-2",
        )
        with (
            self.login(self.streamer),
            self.assertLogs("tournamentcontrol.competition.compops.streams"),
        ):
            self.post(
                "compops:slot-stream",
                slot_key="1040",
                status="live",
                extra=DATASTAR,
                **self.kw,
            )
        self.assertEqual(
            self.openings(),
            [
                (
                    "replace",
                    f'<div id="stream-{self.field1.pk}" class="stream" {HELD}>',
                ),
                ("replace", f'<div id="stream-{field2.pk}" class="stream" {HELD}>'),
            ],
        )

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_a_refused_event_action_holds_the_event_with_the_reason(self, build):
        build.return_value = self.refusing("quota")
        with (
            self.login(self.streamer),
            self.assertLogs("tournamentcontrol.competition.compops.streams"),
        ):
            self.post(
                "compops:event-stream",
                event_pk=self.event.pk,
                status="testing",
                extra=DATASTAR,
                **self.kw,
            )
        ((mode, html),) = element_patches(self.last_response)
        self.assertEqual(mode, "replace")
        self.assertEqual(
            html.splitlines()[0],
            f'<div id="event-{self.event.pk}" class="stream" {HELD}>',
        )
        message = f"{streams.describe(self.event)}: quota"
        self.assertInHTML(f'<p class="warn">{escape(message)}</p>', html, count=1)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_an_action_that_goes_through_releases_every_block(self, build):
        build.return_value = youtube_mock("testing")
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            self.post(
                "compops:match-stream",
                match_pk=self.current.pk,
                status="live",
                extra=DATASTAR,
                **self.kw,
            )
        mode, html = self.column()
        self.assertEqual(mode, "outer")
        self.assertIn(
            f'<div id="stream-{self.field1.pk}" class="stream">', html.splitlines()
        )
        self.assertIn(
            f'<div id="event-{self.event.pk}" class="stream">', html.splitlines()
        )

    def test_the_layout_toggle_holds_every_block(self):
        with self.login(self.streamer):
            self.post("compops:layout", extra=DATASTAR, **self.kw)
        ((mode, html),) = element_patches(self.last_response)
        self.assertEqual(mode, "outer")
        self.assertIn(
            f'<div id="stream-{self.field1.pk}" class="stream" {HELD}>',
            html.splitlines(),
        )
        self.assertIn(
            f'<div id="event-{self.event.pk}" class="stream" {HELD}>',
            html.splitlines(),
        )


class LockedTransitionTests(StreamsFixture):
    @mock.patch("tournamentcontrol.competition.models.build")
    def test_transition_locks_the_row(self, build):
        build.return_value = youtube_mock("testing")
        with CaptureQueriesContext(connection) as queries:
            with self.captureOnCommitCallbacks(execute=True):
                streams.transition(self.current, "live", "op")
        locking = [q["sql"] for q in queries if "FOR UPDATE" in q["sql"]]
        self.assertEqual(len(locking), 1)
        self.assertIn('FOR UPDATE OF "competition_match"', locking[0])

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_stale_instance_carries_the_new_status(self, build):
        build.return_value = youtube_mock("testing")
        stale = Match.objects.get(pk=self.current.pk)
        Match.objects.filter(pk=self.current.pk).update(live_stream_status="ready")
        with self.captureOnCommitCallbacks(execute=True):
            error = streams.transition(stale, "live", "op")
        self.assertEqual(error, None)
        self.assertEqual(stale.live_stream_status, "live")
        self.assertEqual(stale.live_stream_status_at, timezone.now())
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "live")
        self.assertEqual(
            build.return_value.liveBroadcasts.return_value.transition.call_count, 1
        )

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_event_transition_locks_the_row(self, build):
        build.return_value = youtube_mock("ready")
        with CaptureQueriesContext(connection) as queries:
            with self.captureOnCommitCallbacks(execute=True):
                streams.transition(self.event, "testing", "op")
        locking = [q["sql"] for q in queries if "FOR UPDATE" in q["sql"]]
        self.assertEqual(len(locking), 1)
        self.assertIn('FOR UPDATE OF "competition_livestreamevent"', locking[0])
        self.assertEqual(self.event.live_stream_status, "testing")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_deleted_row_reports_an_error_and_publishes_nothing(self, build):
        build.return_value = youtube_mock("ready")
        LiveStreamEvent.objects.filter(pk=self.event.pk).delete()
        with self.assertLogs("tournamentcontrol.competition.compops.streams"):
            with self.captureOnCommitCallbacks(execute=True):
                error = streams.transition(self.event, "testing", "op")
        self.assertEqual(error, f"{self.event.title}: no longer exists")
        self.assertEqual(build.call_count, 0)
        self.assertEqual(events.recent(self.season.pk), [])


class EventAndSlotTransitionTests(StreamsFixture):
    @mock.patch("tournamentcontrol.competition.models.build")
    def test_season_event_transition(self, build):
        build.return_value = youtube_mock("ready")
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            self.send("event-stream", event_pk=self.event.pk, status="testing")
        self.assert_http_302_found(url=self.url("day"))
        self.event.refresh_from_db()
        self.assertEqual(self.event.live_stream_status, "testing")
        (event,) = events.recent(self.season.pk)
        self.assertEqual(event["kind"], "event")

    def test_removed_event_is_not_listed(self):
        removed = factories.LiveStreamEventFactory.create(
            season=self.season,
            title="Removed Ceremony",
            start=timezone.make_aware(datetime.datetime(2026, 10, 8, 18, 0), TZ),
            live_stream=False,
        )
        with self.login(self.streamer):
            self.get("compops:streams", **self.kw)
        self.assertResponseContains(f'<div class="match">{self.event.title}</div>')
        self.assertResponseNotContains(f'<div class="match">{removed.title}</div>')

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_removed_event_transition_is_404(self, build):
        build.return_value = youtube_mock("ready")
        self.event.live_stream = False
        self.event.save()
        with self.login(self.streamer):
            self.send("event-stream", event_pk=self.event.pk, status="testing")
        self.assert_http_404_not_found()
        self.assertEqual(build.call_count, 0)
        self.event.refresh_from_db()
        self.assertEqual(self.event.live_stream_status, None)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_event_on_another_day_is_404(self, build):
        build.return_value = youtube_mock("ready")
        tomorrow = factories.LiveStreamEventFactory.create(
            season=self.season,
            start=timezone.make_aware(datetime.datetime(2026, 10, 9, 17, 30), TZ),
        )
        with self.login(self.streamer):
            self.send("event-stream", event_pk=tomorrow.pk, status="testing")
        self.assert_http_404_not_found()
        self.assertEqual(build.call_count, 0)
        tomorrow.refresh_from_db()
        self.assertEqual(tomorrow.live_stream_status, None)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_slot_transition_skips_matches_not_streamed(self, build):
        service = youtube_mock("testing")
        build.return_value = service
        # A stale identifier on a match turned off for streaming, and one on
        # a ground that is not streamed.
        turned_off = self.make(
            self.current.stage, 10, 40, external_identifier="yt-turned-off"
        )
        field2 = factories.GroundFactory.create(venue=self.field1.venue)
        unstreamed_ground = self.make(
            self.current.stage,
            10,
            40,
            play_at=field2,
            live_stream=True,
            external_identifier="yt-field-2",
        )
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            self.send("slot-stream", slot_key="1040", status="live")
        self.assert_http_302_found(url=self.url("day"))
        service.liveBroadcasts.return_value.transition.assert_called_once_with(
            broadcastStatus="live", id="yt-current", part="snippet,status"
        )
        turned_off.refresh_from_db()
        unstreamed_ground.refresh_from_db()
        self.assertEqual(turned_off.live_stream_status, None)
        self.assertEqual(unstreamed_ground.live_stream_status, None)
        self.assertEqual(len(events.recent(self.season.pk)), 1)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_slot_transition_hits_every_broadcast_in_the_slot(self, build):
        service = youtube_mock("testing")
        build.return_value = service
        other = self.make(
            self.current.stage, 10, 40, live_stream=True, external_identifier="yt-other"
        )
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            self.send("slot-stream", slot_key="1040", status="live")
        self.assert_http_302_found(url=self.url("day"))
        self.assertEqual(service.liveBroadcasts.return_value.transition.call_count, 2)
        other.refresh_from_db()
        self.assertEqual(other.live_stream_status, "live")
        self.assertEqual(len(events.recent(self.season.pk)), 2)
