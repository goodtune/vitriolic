"""
A season with YouTube client details saved, but whose authorisation nobody
has completed, cannot reach YouTube: it has no refresh token, so every request
raises ``RefreshError`` (#658). Whatever would call YouTube for such a season,
or queue a task that would, must leave it alone and say why where it can.
"""

import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.messages import Message
from django.contrib.messages.test import MessagesTestMixin
from google.auth.exceptions import RefreshError
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.admin import YOUTUBE_NOT_AUTHORISED_MESSAGE
from tournamentcontrol.competition.models import LiveStreamEvent, Match
from tournamentcontrol.competition.tasks import (
    delete_youtube_broadcast,
    delete_youtube_stream,
    sync_live_stream,
    sync_live_stream_event,
)
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_mcp_admin import AdminFixtureMixin

CLIENT_DETAILS = {
    "live_stream": True,
    "live_stream_client_id": "client-id",
    "live_stream_client_secret": "client-secret",
}

YOUTUBE = "tournamentcontrol.competition.models.Season.youtube"

# What the first request to YouTube raises for such a season.
NO_REFRESH_TOKEN = RefreshError(
    "The credentials do not contain the necessary fields need to refresh the "
    "access token."
)

EVENT_FORM = {
    "title": "Opening Ceremony",
    "description": "",
    "start_0_year": "2025",
    "start_0_month": "5",
    "start_0_day": "1",
    "start_1": "19",
    "start_2": "0",
    "stop_0_year": "2025",
    "stop_0_month": "5",
    "stop_0_day": "1",
    "stop_1": "20",
    "stop_2": "30",
}


class YouTubeReadyTests(TestCase):
    def test_ready_needs_the_client_details_and_the_refresh_token(self):
        cases = {
            "nothing": ({}, False),
            "client details": (CLIENT_DETAILS, False),
            "token alone": ({"live_stream_refresh_token": "r"}, False),
            "all": ({**CLIENT_DETAILS, "live_stream_refresh_token": "r"}, True),
        }
        for name, (fields, ready) in cases.items():
            with self.subTest(name):
                season = factories.SeasonFactory.build(**fields)
                self.assertIs(season.youtube_ready, ready)


@mock.patch(YOUTUBE, new_callable=mock.PropertyMock, side_effect=NO_REFRESH_TOKEN)
class TaskTests(TestCase):
    """The tasks return quietly; they neither call YouTube nor fail."""

    def setUp(self):
        super().setUp()
        self.season = factories.SeasonFactory.create(timezone="UTC", **CLIENT_DETAILS)

    def test_sync_live_stream(self, youtube):
        match = factories.MatchFactory.create(
            stage__division__season=self.season,
            live_stream=True,
            date=datetime.date(2025, 5, 1),
            time=datetime.time(14, 0),
            datetime=datetime.datetime(2025, 5, 1, 14, 0, tzinfo=ZoneInfo("UTC")),
        )
        self.assertEqual(sync_live_stream(match.pk), None)
        youtube.assert_not_called()

    def test_sync_live_stream_event(self, youtube):
        event = factories.LiveStreamEventFactory.create(season=self.season)
        self.assertEqual(sync_live_stream_event(event.pk), None)
        youtube.assert_not_called()

    def test_delete_youtube_broadcast(self, youtube):
        self.assertEqual(delete_youtube_broadcast(self.season.pk, "adhoc123"), None)
        youtube.assert_not_called()

    def test_delete_youtube_stream(self, youtube):
        self.assertEqual(delete_youtube_stream(self.season.pk, "stream123"), None)
        youtube.assert_not_called()


class SignalTests(TestCase):
    """Deleting a record queues no clean-up that could not be carried out."""

    def setUp(self):
        super().setUp()
        self.season = factories.SeasonFactory.create(**CLIENT_DETAILS)

    @mock.patch(
        "tournamentcontrol.competition.signals.live_streams.delete_youtube_broadcast"
    )
    def test_deleted_event_queues_no_broadcast_removal(self, task):
        event = factories.LiveStreamEventFactory.create(season=self.season)
        with self.captureOnCommitCallbacks(execute=True):
            event.delete()
        task.s.assert_not_called()

    @mock.patch(
        "tournamentcontrol.competition.signals.live_streams.delete_youtube_stream"
    )
    def test_deleted_stream_key_queues_no_stream_removal(self, task):
        key = factories.LiveStreamKeyFactory.create(season=self.season)
        with self.captureOnCommitCallbacks(execute=True):
            key.delete()
        task.s.assert_not_called()


@mock.patch(YOUTUBE, new_callable=mock.PropertyMock, side_effect=NO_REFRESH_TOKEN)
class AdminTests(MessagesTestMixin, TestCase):
    """The admin says the season is not authorised, and calls nothing."""

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.season = factories.SeasonFactory.create(timezone="UTC", **CLIENT_DETAILS)
        self.stage = factories.StageFactory.create(division__season=self.season)
        self.ground = factories.GroundFactory.create(
            venue__season=self.season, live_stream=True
        )
        self.match = factories.MatchFactory.create(
            stage=self.stage,
            play_at=self.ground,
            live_stream=True,
            external_identifier="yt-match",
            date=datetime.date(2025, 5, 1),
            time=datetime.time(14, 0),
            datetime=datetime.datetime(2025, 5, 1, 14, 0, tzinfo=ZoneInfo("UTC")),
        )

    def assertNotAuthorised(self):
        self.assertMessages(
            self.last_response,
            [Message(messages.ERROR, str(YOUTUBE_NOT_AUTHORISED_MESSAGE))],
        )

    @mock.patch("tournamentcontrol.competition.admin.sync_live_stream_event")
    def test_add_live_stream_event_is_refused(self, task, youtube):
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:livestreamevent:add",
                self.season.competition_id,
                self.season.pk,
                data=EVENT_FORM,
            )
        self.assert_http_302_found()
        self.assertNotAuthorised()
        youtube.assert_not_called()
        task.s.assert_not_called()
        self.assertEqual(self.season.live_stream_events.count(), 0)

    @mock.patch("tournamentcontrol.competition.admin.sync_live_stream_event")
    def test_edit_live_stream_event_is_saved_and_queues_no_sync(self, task, youtube):
        event = factories.LiveStreamEventFactory.create(season=self.season)
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:livestreamevent:edit",
                self.season.competition_id,
                self.season.pk,
                event.pk,
                data=EVENT_FORM,
            )
        self.assert_http_302_found()
        event.refresh_from_db()
        self.assertEqual(event.title, "Opening Ceremony")
        task.s.assert_not_called()
        youtube.assert_not_called()

    def test_delete_live_stream_event_is_blocked(self, youtube):
        event = factories.LiveStreamEventFactory.create(season=self.season)
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:livestreamevent:delete",
                self.season.competition_id,
                self.season.pk,
                event.pk,
            )
        self.assert_http_302_found()
        self.assertMessages(
            self.last_response,
            [
                Message(
                    messages.ERROR,
                    "YouTube access has not been authorised for this season; "
                    "unable to confirm the live stream event has been removed "
                    "from the platform.",
                )
            ],
        )
        youtube.assert_not_called()
        self.assertEqual(LiveStreamEvent.objects.filter(pk=event.pk).count(), 1)

    @mock.patch("tournamentcontrol.competition.admin.sync_live_stream")
    def test_edit_match_is_saved_and_queues_no_sync(self, task, youtube):
        edit = self.match.url_names["edit"]
        with self.login(self.superuser):
            self.post(
                edit.url_name,
                *edit.args,
                data={
                    "home_team": self.match.home_team_id,
                    "away_team": self.match.away_team_id,
                    "label": "Grand Final",
                    "round": 1,
                    "date": "2025-05-01",
                    "time": "14:00:00",
                    "play_at": self.ground.pk,
                    "include_in_ladder": "1",
                    "live_stream": "1",
                    "live_stream_thumbnail_image-clear": "0",
                    "live_stream_thumbnail_image": "",
                },
            )
        self.assert_http_302_found(url=str(self.stage.urls["edit"]))
        self.match.refresh_from_db()
        self.assertEqual(self.match.label, "Grand Final")
        task.s.assert_not_called()

    @mock.patch("tournamentcontrol.competition.admin.sync_live_stream")
    def test_day_of_matches_is_saved_and_queues_no_sync(self, task, youtube):
        Match.objects.filter(pk=self.match.pk).update(live_stream=False)
        with self.login(self.superuser):
            self.post(
                "admin:fixja:match-live-stream",
                self.season.competition_id,
                self.season.pk,
                "20250501",
                data={
                    "form-TOTAL_FORMS": "1",
                    "form-INITIAL_FORMS": "1",
                    "form-MIN_NUM_FORMS": "0",
                    "form-MAX_NUM_FORMS": "1000",
                    "form-0-id": str(self.match.pk),
                    "form-0-live_stream": "1",
                },
            )
        self.assert_http_302_found(url=str(self.season.urls["edit"]))
        self.match.refresh_from_db()
        self.assertIs(self.match.live_stream, True)
        task.s.assert_not_called()

    @mock.patch("tournamentcontrol.competition.admin.sync_live_stream")
    def test_match_resync_is_refused(self, task, youtube):
        resync = self.match.url_names["resync-live-stream"]
        with self.login(self.superuser):
            self.post(resync.url_name, *resync.args)
        self.assert_http_302_found(url=str(self.stage.urls["edit"]))
        self.assertNotAuthorised()
        task.s.assert_not_called()

    @mock.patch("tournamentcontrol.competition.admin.sync_live_stream")
    def test_day_resync_is_refused(self, task, youtube):
        with self.login(self.superuser):
            self.post(
                "admin:fixja:match-live-stream-resync",
                self.season.competition_id,
                self.season.pk,
                "20250501",
            )
        self.assert_http_302_found(url=str(self.season.urls["edit"]))
        self.assertNotAuthorised()
        task.s.assert_not_called()


@mock.patch("tournamentcontrol.competition.mcp.admin.sync_live_stream_event")
@mock.patch("tournamentcontrol.competition.mcp.admin.sync_live_stream")
@mock.patch(YOUTUBE, new_callable=mock.PropertyMock, side_effect=NO_REFRESH_TOKEN)
class MCPTests(AdminFixtureMixin, TestCase):
    """The MCP tools say the same, and queue nothing."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for field, value in CLIENT_DETAILS.items():
            setattr(cls.season, field, value)
        cls.season.save()
        cls.event = factories.LiveStreamEventFactory.create(season=cls.season)

    def test_tool_that_calls_youtube_is_refused(self, youtube, sync, sync_event):
        self.assertToolError(
            str(YOUTUBE_NOT_AUTHORISED_MESSAGE),
            self.admin().create_season_stream_key,
            self.season.pk,
            title="Camera",
        )
        youtube.assert_not_called()

    def test_match_change_queues_no_sync(self, youtube, sync, sync_event):
        Match.objects.filter(pk=self.fra_v_eng.pk).update(external_identifier="yt-1")
        res = self.admin().update_match(self.fra_v_eng.pk, label="Grand Final")
        self.assertEqual(
            (res["match"]["label"], res["live_stream_sync_queued"]),
            ("Grand Final", False),
        )
        sync.s.assert_not_called()

    def test_event_change_queues_no_sync(self, youtube, sync, sync_event):
        res = self.admin().update_season_stream_event(
            self.season.pk, self.event.pk, title="Renamed"
        )
        self.assertEqual(
            (res["event"]["title"], res["live_stream_sync_queued"]),
            ("Renamed", False),
        )
        sync_event.s.assert_not_called()
