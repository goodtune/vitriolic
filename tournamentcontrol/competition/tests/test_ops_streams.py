import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from test_plus import TestCase

from tournamentcontrol.competition.ops import events
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_live_stream_transition import (
    YOUTUBE_SEASON,
    youtube_mock,
)

TZ = ZoneInfo("Australia/Brisbane")


@freeze_time("2026-10-08 10:50 +10:00")
class StreamsFixture(TestCase):
    def setUp(self):
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
            stage, 10, 40, external_identifier="yt-current", live_stream_status="testing"
        )
        self.following = self.make(stage, 11, 20, external_identifier="yt-next")
        self.event = factories.LiveStreamEventFactory.create(
            season=self.season,
            start=timezone.make_aware(datetime.datetime(2026, 10, 8, 17, 30), TZ),
        )
        self.kw = {"competition": "pacific-cup", "season": "pc26", "datestr": "20261008"}

    def make(self, stage, hour, minute, **kwargs):
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, hour, minute), TZ)
        return factories.MatchFactory.create(
            stage=stage,
            datetime=when,
            date=when.date(),
            time=when.time(),
            play_at=self.field1,
            **kwargs,
        )

    def url(self, name, **extra):
        return reverse(f"ops:{name}", kwargs={**self.kw, **extra})


class StreamsFragmentTests(StreamsFixture):
    def test_current_match_with_status_and_buttons(self):
        with self.login(self.streamer):
            self.get("ops:streams", **self.kw)
        self.assertResponseContains('<span class="badge testing">testing</span>')
        self.assertResponseContains(
            '<button class="btn g sm" type="submit">Go live</button>'
        )

    def test_live_starting_counts_as_live(self):
        self.current.live_stream_status = "liveStarting"
        self.current.save()
        with self.login(self.streamer):
            self.get("ops:day", **self.kw)
        self.assertResponseContains('<span id="streams-count" class="count">1</span>')
        self.assertResponseContains(
            '<button class="btn r sm" type="submit">End</button>'
        )

    def test_without_permission_no_buttons(self):
        with self.login(self.staff):
            self.get("ops:streams", **self.kw)
        self.assertResponseNotContains("Go live")

    def test_next_match_and_season_event_listed(self):
        with self.login(self.streamer):
            self.get("ops:streams", **self.kw)
        self.assertResponseContains('<span class="badge none">no status</span>')
        self.assertResponseContains('<div class="match">%s</div>' % self.event.title)

    def test_event_time_is_shown_in_the_season_timezone(self):
        with self.login(self.streamer):
            self.get("ops:streams", **self.kw)
        self.assertResponseContains('<div class="ground">17:30</div>')


class MatchTransitionTests(StreamsFixture):
    @mock.patch("tournamentcontrol.competition.models.build")
    def test_go_live_stores_status_and_publishes(self, build):
        build.return_value = youtube_mock("testing")
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.url("match-stream", match_pk=self.current.pk, status="live"),
                headers={"Datastar-Request": "true"},
            )
        body = b"".join(response.streaming_content).decode()
        self.assertIn('data: elements <span class="badge live">live</span>', body)
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "live")
        (event,) = events.recent(self.season.pk)
        self.assertEqual(event["type"], "stream-changed")
        self.assertEqual(event["status"], "live")
        self.assertEqual(
            event["summary"],
            "Field 1 · %s v %s → live"
            % (self.current.home_team.title, self.current.away_team.title),
        )

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_plain_post_redirects(self, build):
        build.return_value = youtube_mock("testing")
        with self.login(self.streamer):
            response = self.client.post(
                self.url("match-stream", match_pk=self.current.pk, status="live")
            )
        self.assertRedirects(
            response, reverse("ops:day", kwargs=self.kw), fetch_redirect_response=False
        )

    def test_without_permission_is_403(self):
        with self.login(self.staff):
            response = self.client.post(
                self.url("match-stream", match_pk=self.current.pk, status="live")
            )
        self.assertEqual(response.status_code, 403)

    def test_unknown_status_is_404(self):
        with self.login(self.streamer):
            response = self.client.post(
                self.url("match-stream", match_pk=self.current.pk, status="paused")
            )
        self.assertEqual(response.status_code, 404)

    def test_get_is_not_allowed(self):
        with self.login(self.streamer):
            response = self.client.get(
                self.url("match-stream", match_pk=self.current.pk, status="live")
            )
        self.assertEqual(response.status_code, 405)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_missing_broadcast_reports_an_error_and_publishes_nothing(self, build):
        build.return_value = youtube_mock()
        orphan = self.make(self.current.stage, 12, 0)
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.url("match-stream", match_pk=orphan.pk, status="live"),
                headers={"Datastar-Request": "true"},
            )
        body = b"".join(response.streaming_content).decode()
        self.assertIn("does not have a live stream identifier", body)
        self.assertEqual(events.recent(self.season.pk), [])

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_expired_credentials_report_an_error_and_publish_nothing(self, build):
        build.side_effect = RefreshError("expired")
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            with self.assertLogs("tournamentcontrol.competition.ops.streams"):
                response = self.client.post(
                    self.url("match-stream", match_pk=self.current.pk, status="live"),
                    headers={"Datastar-Request": "true"},
                )
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content).decode()
        self.assertIn("expired", body)
        self.assertEqual(events.recent(self.season.pk), [])

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_youtube_api_error_reports_the_reason_and_publishes_nothing(self, build):
        service = youtube_mock("testing")
        service.liveBroadcasts.return_value.transition.return_value.execute.side_effect = HttpError(
            resp=mock.Mock(status=403, reason="quota"), content=b"quota"
        )
        build.return_value = service
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            with self.assertLogs("tournamentcontrol.competition.ops.streams"):
                response = self.client.post(
                    self.url("match-stream", match_pk=self.current.pk, status="live"),
                    headers={"Datastar-Request": "true"},
                )
        body = b"".join(response.streaming_content).decode()
        self.assertIn("quota", body)
        self.assertEqual(events.recent(self.season.pk), [])


class EventAndSlotTransitionTests(StreamsFixture):
    @mock.patch("tournamentcontrol.competition.models.build")
    def test_season_event_transition(self, build):
        build.return_value = youtube_mock("ready")
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                self.url("event-stream", event_pk=self.event.pk, status="testing")
            )
        self.event.refresh_from_db()
        self.assertEqual(self.event.live_stream_status, "testing")
        (event,) = events.recent(self.season.pk)
        self.assertEqual(event["kind"], "event")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_slot_transition_hits_every_broadcast_in_the_slot(self, build):
        service = youtube_mock("testing")
        build.return_value = service
        other = self.make(self.current.stage, 10, 40, external_identifier="yt-other")
        with self.login(self.streamer), self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url("slot-stream", slot_key="1040", status="live"))
        self.assertEqual(service.liveBroadcasts.return_value.transition.call_count, 2)
        other.refresh_from_db()
        self.assertEqual(other.live_stream_status, "live")
        self.assertEqual(len(events.recent(self.season.pk)), 2)
