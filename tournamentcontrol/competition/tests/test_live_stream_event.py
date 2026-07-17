"""
Tests for adhoc live stream events associated with a competition Season.
"""

import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.forms import LiveStreamEventForm
from tournamentcontrol.competition.models import LiveStreamEvent, LiveStreamKey
from tournamentcontrol.competition.tasks import (
    build_live_stream_event_body,
    delete_youtube_broadcast,
    delete_youtube_stream,
    sync_live_stream_event,
)
from tournamentcontrol.competition.tests import factories

UTC = ZoneInfo("UTC")


class LiveStreamEventModelTests(TestCase):
    def test_str_is_title(self):
        event = factories.LiveStreamEventFactory.create(title="Opening Ceremony")
        self.assertEqual(str(event), "Opening Ceremony")

    def test_clean_rejects_stop_before_start(self):
        event = factories.LiveStreamEventFactory.create()
        event.stop = event.start - datetime.timedelta(minutes=30)
        with self.assertRaises(ValidationError) as cm:
            event.clean()
        self.assertIn("stop", cm.exception.message_dict)

    def test_clean_rejects_stop_equal_to_start(self):
        event = factories.LiveStreamEventFactory.create()
        event.stop = event.start
        with self.assertRaises(ValidationError) as cm:
            event.clean()
        self.assertIn("stop", cm.exception.message_dict)

    def test_clean_rejects_stream_key_from_another_season(self):
        event = factories.LiveStreamEventFactory.create()
        other_key = factories.LiveStreamKeyFactory.create()
        event.stream_key = other_key
        with self.assertRaises(ValidationError) as cm:
            event.clean()
        self.assertIn("stream_key", cm.exception.message_dict)

    def test_clean_accepts_stream_key_from_same_season(self):
        event = factories.LiveStreamEventFactory.create()
        event.stream_key = factories.LiveStreamKeyFactory.create(season=event.season)
        self.assertEqual(event.clean(), None)

    def test_thumbnail_prefers_event_image(self):
        event = factories.LiveStreamEventFactory.create(
            season__live_stream_thumbnail_image=b"season-bytes",
            live_stream_thumbnail_image=b"event-bytes",
        )
        media = event.get_thumbnail_media_upload()
        self.assertEqual(media.getbytes(0, 11), b"event-bytes")

    def test_thumbnail_falls_back_to_season_image(self):
        event = factories.LiveStreamEventFactory.create(
            season__live_stream_thumbnail_image=b"season-bytes",
        )
        media = event.get_thumbnail_media_upload()
        self.assertEqual(media.getbytes(0, 12), b"season-bytes")

    def test_thumbnail_none_when_no_images(self):
        event = factories.LiveStreamEventFactory.create()
        self.assertEqual(event.get_thumbnail_media_upload(), None)

    def test_admin_urls(self):
        event = factories.LiveStreamEventFactory.create()
        self.assertEqual(
            str(event.urls["edit"]),
            self.reverse(
                "admin:fixja:competition:season:livestreamevent:edit",
                event.season.competition_id,
                event.season_id,
                event.pk,
            ),
        )
        self.assertCountEqual(event.urls.keys(), ["add", "edit", "delete"])

    def test_season_relation(self):
        event = factories.LiveStreamEventFactory.create()
        self.assertCountEqual(event.season.live_stream_events.all(), [event])


class LiveStreamKeyModelTests(TestCase):
    def test_str_without_generated_key_is_title(self):
        stream_key = factories.LiveStreamKeyFactory.create(title="Roaming Camera")
        self.assertEqual(str(stream_key), "Roaming Camera")

    def test_str_with_generated_key_includes_key(self):
        stream_key = factories.LiveStreamKeyFactory.create(
            title="Roaming Camera", stream_key="abcd-1234"
        )
        self.assertEqual(str(stream_key), "Roaming Camera (abcd-1234)")

    def test_season_relation(self):
        stream_key = factories.LiveStreamKeyFactory.create()
        self.assertCountEqual(stream_key.season.live_stream_keys.all(), [stream_key])

    def test_admin_urls(self):
        stream_key = factories.LiveStreamKeyFactory.create()
        self.assertEqual(
            str(stream_key.urls["edit"]),
            self.reverse(
                "admin:fixja:competition:season:livestreamkey:edit",
                stream_key.season.competition_id,
                stream_key.season_id,
                stream_key.pk,
            ),
        )
        self.assertCountEqual(stream_key.urls.keys(), ["add", "edit", "delete"])

    def test_protected_while_referenced_by_event(self):
        stream_key = factories.LiveStreamKeyFactory.create()
        factories.LiveStreamEventFactory.create(
            season=stream_key.season, stream_key=stream_key
        )
        with self.assertRaises(ProtectedError):
            stream_key.delete()


class LiveStreamEventFormTests(TestCase):
    def test_stream_key_choices_limited_to_season_pool(self):
        event = factories.LiveStreamEventFactory.create()
        stream_key = factories.LiveStreamKeyFactory.create(season=event.season)
        factories.LiveStreamKeyFactory.create()  # another season entirely
        form = LiveStreamEventForm(instance=event)
        self.assertCountEqual(form.fields["stream_key"].queryset, [stream_key])

    def test_stop_before_start_is_invalid(self):
        season = factories.SeasonFactory.create()
        form = LiveStreamEventForm(
            instance=LiveStreamEvent(season=season),
            data={
                "title": "Opening Ceremony",
                "description": "",
                "start_0": "2025-05-01",
                "start_1": "19:00:00",
                "start_2": "UTC",
                "stop_0": "2025-05-01",
                "stop_1": "18:00:00",
                "stop_2": "UTC",
                "live_stream": "1",
            },
        )
        self.assertEqual(form.is_valid(), False)
        self.assertIn("stop", form.errors)

    def test_valid_form_saves_event(self):
        season = factories.SeasonFactory.create()
        stream_key = factories.LiveStreamKeyFactory.create(season=season)
        form = LiveStreamEventForm(
            instance=LiveStreamEvent(season=season),
            data={
                "title": "Opening Ceremony",
                "description": "Live from the main field.",
                "start_0": "2025-05-01",
                "start_1": "19:00:00",
                "start_2": "UTC",
                "stop_0": "2025-05-01",
                "stop_1": "20:30:00",
                "stop_2": "UTC",
                "stream_key": str(stream_key.pk),
                "live_stream": "1",
            },
        )
        self.assertEqual(form.is_valid(), True, form.errors)
        event = form.save()
        self.assertEqual(event.season, season)
        self.assertEqual(
            event.start, datetime.datetime(2025, 5, 1, 19, 0, tzinfo=UTC)
        )
        self.assertEqual(
            event.stop, datetime.datetime(2025, 5, 1, 20, 30, tzinfo=UTC)
        )
        self.assertEqual(event.stream_key, stream_key)


class BuildLiveStreamEventBodyTests(TestCase):
    def test_body_uses_event_details(self):
        event = factories.LiveStreamEventFactory.create(
            title="Grand Final Presentation",
            description="Trophy presentation and speeches.",
            start=datetime.datetime(2025, 5, 3, 6, 0, tzinfo=UTC),
            stop=datetime.datetime(2025, 5, 3, 7, 30, tzinfo=UTC),
            season__live_stream_privacy="unlisted",
        )
        body = build_live_stream_event_body(event)
        self.assertEqual(body["snippet"]["title"], "Grand Final Presentation")
        self.assertEqual(
            body["snippet"]["description"], "Trophy presentation and speeches."
        )
        self.assertEqual(
            body["snippet"]["scheduledStartTime"], "2025-05-03T06:00:00+00:00"
        )
        self.assertEqual(
            body["snippet"]["scheduledEndTime"], "2025-05-03T07:30:00+00:00"
        )
        self.assertEqual(body["status"]["privacyStatus"], "unlisted")

    def test_body_normalises_to_utc(self):
        sydney = ZoneInfo("Australia/Sydney")
        event = factories.LiveStreamEventFactory.create(
            start=datetime.datetime(2025, 5, 3, 16, 0, tzinfo=sydney),
            stop=datetime.datetime(2025, 5, 3, 17, 0, tzinfo=sydney),
        )
        body = build_live_stream_event_body(event)
        self.assertEqual(
            body["snippet"]["scheduledStartTime"], "2025-05-03T06:00:00+00:00"
        )
        self.assertEqual(
            body["snippet"]["scheduledEndTime"], "2025-05-03T07:00:00+00:00"
        )


class SyncLiveStreamEventTests(TestCase):
    def _event(self, **kwargs):
        kwargs.setdefault("season__live_stream", True)
        kwargs.setdefault("season__live_stream_client_id", "client-id")
        kwargs.setdefault("season__live_stream_client_secret", "client-secret")
        return factories.LiveStreamEventFactory.create(**kwargs)

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_insert_sets_external_identifier(self, mock_youtube_prop):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        mock_youtube.liveBroadcasts.return_value.insert.return_value.execute.return_value = {
            "id": "adhoc123"
        }

        event = self._event()
        sync_live_stream_event(event.pk)

        mock_youtube.liveBroadcasts.return_value.insert.assert_called_once()
        event.refresh_from_db()
        self.assertEqual(event.external_identifier, "adhoc123")

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_insert_binds_to_selected_stream_key(self, mock_youtube_prop):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        mock_youtube.liveBroadcasts.return_value.insert.return_value.execute.return_value = {
            "id": "adhoc123"
        }
        mock_youtube.liveBroadcasts.return_value.bind.return_value.execute.return_value = {
            "contentDetails": {"boundStreamId": "stream456"}
        }

        event = self._event()
        event.stream_key = factories.LiveStreamKeyFactory.create(
            season=event.season,
            external_identifier="stream456",
            stream_key="abcd-1234",
        )
        event.save()

        sync_live_stream_event(event.pk)

        mock_youtube.liveBroadcasts.return_value.bind.assert_called_once_with(
            part="id,snippet,contentDetails,status",
            id="adhoc123",
            streamId="stream456",
        )
        event.refresh_from_db()
        self.assertEqual(event.live_stream_bind, "stream456")

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_unbinds_when_stream_key_removed(self, mock_youtube_prop):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube

        event = self._event(
            external_identifier="adhoc123", live_stream_bind="stream456"
        )
        sync_live_stream_event(event.pk)

        mock_youtube.liveBroadcasts.return_value.bind.assert_called_once_with(
            part="id,snippet,contentDetails,status",
            id="adhoc123",
        )
        event.refresh_from_db()
        self.assertEqual(event.live_stream_bind, None)

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_update_existing_broadcast(self, mock_youtube_prop):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube

        event = self._event(external_identifier="adhoc123")
        sync_live_stream_event(event.pk)

        mock_youtube.liveBroadcasts.return_value.update.assert_called_once()
        body = mock_youtube.liveBroadcasts.return_value.update.call_args.kwargs[
            "body"
        ]
        self.assertEqual(body["id"], "adhoc123")
        mock_youtube.liveBroadcasts.return_value.insert.assert_not_called()

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_disable_live_stream_deletes_broadcast(self, mock_youtube_prop):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube

        event = self._event(
            external_identifier="adhoc123",
            live_stream=False,
            live_stream_bind="stream456",
        )
        sync_live_stream_event(event.pk)

        mock_youtube.liveBroadcasts.return_value.delete.assert_called_once_with(
            id="adhoc123"
        )
        event.refresh_from_db()
        self.assertEqual(event.external_identifier, None)
        self.assertEqual(event.live_stream_bind, None)

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_no_credentials_skips_api(self, mock_youtube_prop):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube

        event = factories.LiveStreamEventFactory.create()
        sync_live_stream_event(event.pk)

        mock_youtube.liveBroadcasts.assert_not_called()

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_returns_quietly_when_event_was_deleted(self, mock_youtube_prop):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube

        event = self._event()
        pk = event.pk
        event.delete()
        sync_live_stream_event(pk)

        mock_youtube.liveBroadcasts.assert_not_called()

    @mock.patch("tournamentcontrol.competition.tasks.set_live_stream_event_thumbnail")
    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_insert_queues_thumbnail_when_available(
        self, mock_youtube_prop, mock_thumbnail
    ):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        mock_youtube.liveBroadcasts.return_value.insert.return_value.execute.return_value = {
            "id": "adhoc123"
        }

        event = self._event(live_stream_thumbnail_image=b"event-bytes")
        sync_live_stream_event(event.pk)

        mock_thumbnail.s.assert_called_once_with(event.pk)


class DeleteYoutubeBroadcastTests(TestCase):
    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_deletes_broadcast(self, mock_youtube_prop):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube

        season = factories.SeasonFactory.create(
            live_stream=True,
            live_stream_client_id="client-id",
            live_stream_client_secret="client-secret",
        )
        delete_youtube_broadcast(season.pk, "adhoc123")

        mock_youtube.liveBroadcasts.return_value.delete.assert_called_once_with(
            id="adhoc123"
        )

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_no_credentials_skips_api(self, mock_youtube_prop):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube

        season = factories.SeasonFactory.create()
        delete_youtube_broadcast(season.pk, "adhoc123")

        mock_youtube.liveBroadcasts.assert_not_called()


class LiveStreamEventAdminTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def test_season_edit_lists_events_when_live_stream_enabled(self):
        event = factories.LiveStreamEventFactory.create(
            title="Opening Ceremony", season__live_stream=True
        )
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:competition:season:edit",
                event.season.competition_id,
                event.season_id,
            )
            self.assertResponseContains("Opening Ceremony", html=False)
            self.assertResponseContains("live_stream_events-tab", html=False)

    def test_season_edit_hides_events_tab_when_not_live_streamed(self):
        season = factories.SeasonFactory.create(live_stream=False)
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:competition:season:edit",
                season.competition_id,
                season.pk,
            )
            self.assertResponseNotContains("live_stream_events-tab", html=False)

    def test_add_event_requires_login(self):
        season = factories.SeasonFactory.create(live_stream=True)
        self.assertLoginRequired(
            "admin:fixja:competition:season:livestreamevent:add",
            season.competition_id,
            season.pk,
        )

    @mock.patch("tournamentcontrol.competition.admin.sync_live_stream_event")
    def test_add_event_queues_sync_when_configured(self, mock_task):
        season = factories.SeasonFactory.create(
            live_stream=True,
            live_stream_client_id="client-id",
            live_stream_client_secret="client-secret",
        )
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:livestreamevent:add",
                season.competition_id,
                season.pk,
                data={
                    "title": "Opening Ceremony",
                    "description": "",
                    "start_0": "2025-05-01",
                    "start_1": "19:00:00",
                    "start_2": "UTC",
                    "stop_0": "2025-05-01",
                    "stop_1": "20:30:00",
                    "stop_2": "UTC",
                    "live_stream": "1",
                },
            )
            self.response_302()

        event = season.live_stream_events.get()
        self.assertEqual(event.title, "Opening Ceremony")
        mock_task.s.assert_called_once_with(event.pk)

    @mock.patch("tournamentcontrol.competition.admin.sync_live_stream_event")
    def test_add_event_does_not_queue_sync_without_credentials(self, mock_task):
        season = factories.SeasonFactory.create(live_stream=True)
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:livestreamevent:add",
                season.competition_id,
                season.pk,
                data={
                    "title": "Opening Ceremony",
                    "description": "",
                    "start_0": "2025-05-01",
                    "start_1": "19:00:00",
                    "start_2": "UTC",
                    "stop_0": "2025-05-01",
                    "stop_1": "20:30:00",
                    "stop_2": "UTC",
                    "live_stream": "1",
                },
            )
            self.response_302()

        self.assertEqual(season.live_stream_events.count(), 1)
        mock_task.s.assert_not_called()

    @mock.patch("tournamentcontrol.competition.admin.delete_youtube_broadcast")
    def test_delete_event_queues_broadcast_cleanup(self, mock_task):
        event = factories.LiveStreamEventFactory.create(
            season__live_stream=True,
            season__live_stream_client_id="client-id",
            season__live_stream_client_secret="client-secret",
            external_identifier="adhoc123",
        )
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:livestreamevent:delete",
                event.season.competition_id,
                event.season_id,
                event.pk,
            )
            self.response_302()

        self.assertEqual(LiveStreamEvent.objects.count(), 0)
        mock_task.s.assert_called_once_with(event.season.pk, "adhoc123")

    @mock.patch("tournamentcontrol.competition.admin.delete_youtube_broadcast")
    def test_delete_event_without_broadcast_skips_cleanup(self, mock_task):
        event = factories.LiveStreamEventFactory.create(season__live_stream=True)
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:livestreamevent:delete",
                event.season.competition_id,
                event.season_id,
                event.pk,
            )
            self.response_302()

        self.assertEqual(LiveStreamEvent.objects.count(), 0)
        mock_task.s.assert_not_called()


class DeleteYoutubeStreamTests(TestCase):
    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_deletes_stream(self, mock_youtube_prop):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube

        season = factories.SeasonFactory.create(
            live_stream=True,
            live_stream_client_id="client-id",
            live_stream_client_secret="client-secret",
        )
        delete_youtube_stream(season.pk, "stream456")

        mock_youtube.liveStreams.return_value.delete.assert_called_once_with(
            id="stream456"
        )

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_no_credentials_skips_api(self, mock_youtube_prop):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube

        season = factories.SeasonFactory.create()
        delete_youtube_stream(season.pk, "stream456")

        mock_youtube.liveStreams.assert_not_called()


class LiveStreamKeyAdminTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def test_season_edit_lists_stream_keys_when_live_stream_enabled(self):
        stream_key = factories.LiveStreamKeyFactory.create(
            title="Roaming Camera", season__live_stream=True
        )
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:competition:season:edit",
                stream_key.season.competition_id,
                stream_key.season_id,
            )
            self.assertResponseContains("Roaming Camera", html=False)
            self.assertResponseContains("live_stream_keys-tab", html=False)

    def test_edit_view_renders(self):
        stream_key = factories.LiveStreamKeyFactory.create(season__live_stream=True)
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:season:livestreamkey:edit",
                stream_key.season.competition_id,
                stream_key.season_id,
                stream_key.pk,
            )
            self.response_200()

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_add_stream_key_generates_key_on_youtube(self, mock_youtube_prop):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        mock_youtube.liveStreams.return_value.insert.return_value.execute.return_value = {
            "id": "stream456",
            "cdn": {"ingestionInfo": {"streamName": "abcd-1234"}},
        }

        season = factories.SeasonFactory.create(
            live_stream=True,
            live_stream_client_id="client-id",
            live_stream_client_secret="client-secret",
        )
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:livestreamkey:add",
                season.competition_id,
                season.pk,
                data={"title": "Roaming Camera"},
            )
            self.response_302()

        stream_key = season.live_stream_keys.get()
        self.assertEqual(stream_key.title, "Roaming Camera")
        self.assertEqual(stream_key.external_identifier, "stream456")
        self.assertEqual(stream_key.stream_key, "abcd-1234")

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_add_stream_key_without_credentials_skips_youtube(
        self, mock_youtube_prop
    ):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube

        season = factories.SeasonFactory.create(live_stream=True)
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:livestreamkey:add",
                season.competition_id,
                season.pk,
                data={"title": "Roaming Camera"},
            )
            self.response_302()

        mock_youtube.liveStreams.assert_not_called()
        stream_key = season.live_stream_keys.get()
        self.assertEqual(stream_key.stream_key, None)
        self.assertEqual(stream_key.external_identifier, None)

    @mock.patch("tournamentcontrol.competition.admin.delete_youtube_stream")
    def test_delete_stream_key_queues_stream_cleanup(self, mock_task):
        stream_key = factories.LiveStreamKeyFactory.create(
            season__live_stream=True,
            season__live_stream_client_id="client-id",
            season__live_stream_client_secret="client-secret",
            external_identifier="stream456",
            stream_key="abcd-1234",
        )
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:livestreamkey:delete",
                stream_key.season.competition_id,
                stream_key.season_id,
                stream_key.pk,
            )
            self.response_302()

        self.assertEqual(LiveStreamKey.objects.count(), 0)
        mock_task.s.assert_called_once_with(stream_key.season.pk, "stream456")

    @mock.patch("tournamentcontrol.competition.admin.delete_youtube_stream")
    def test_delete_stream_key_in_use_is_refused(self, mock_task):
        stream_key = factories.LiveStreamKeyFactory.create(
            season__live_stream=True,
            season__live_stream_client_id="client-id",
            season__live_stream_client_secret="client-secret",
            external_identifier="stream456",
            stream_key="abcd-1234",
        )
        factories.LiveStreamEventFactory.create(
            season=stream_key.season, stream_key=stream_key
        )
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:livestreamkey:delete",
                stream_key.season.competition_id,
                stream_key.season_id,
                stream_key.pk,
            )
            self.response_302()

        # The record is protected while an event references it, so it must
        # still exist and no cleanup may be queued against the platform.
        self.assertEqual(LiveStreamKey.objects.count(), 1)
        mock_task.s.assert_not_called()
