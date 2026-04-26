"""
Tests for the asynchronous live stream synchronization task.
"""

from datetime import date, datetime, time
from unittest import mock
from zoneinfo import ZoneInfo

from django.template import Context, Template
from googleapiclient.errors import HttpError
from test_plus import TestCase

from tournamentcontrol.competition.tasks import (
    _ShortTitle,
    _is_title_too_long,
    build_live_stream_body,
    sync_live_stream,
)
from tournamentcontrol.competition.tests import factories


def _http_error(status, message):
    resp = mock.Mock(status=status, reason="Bad Request")
    content = (
        b'{"error": {"errors": [{"reason": "invalidValue", "message": "'
        + message.encode()
        + b'"}], "code": '
        + str(status).encode()
        + b', "message": "'
        + message.encode()
        + b'"}}'
    )
    return HttpError(resp=resp, content=content)


class IsTitleTooLongTests(TestCase):
    """Detect title-length errors from a YouTube HttpError."""

    def test_detects_title_max_length(self):
        exc = _http_error(400, "title is too long")
        self.assertEqual(True, _is_title_too_long(exc))

    def test_detects_invalid_value_with_title(self):
        exc = _http_error(400, "Invalid title value: invalidValue")
        self.assertEqual(True, _is_title_too_long(exc))

    def test_ignores_unrelated_errors(self):
        exc = _http_error(403, "quotaExceeded")
        self.assertEqual(False, _is_title_too_long(exc))


class BuildLiveStreamBodyShortTitleTests(TestCase):
    """Verify ``short=True`` swaps in ``short_title`` for the templated names."""

    def setUp(self):
        self.season = factories.SeasonFactory.create(
            title="Premiership Season Two Thousand Twenty Five",
            short_title="PS25",
            live_stream_privacy="unlisted",
        )
        self.division = factories.DivisionFactory.create(
            season=self.season,
            title="Mens Open Division Premier Tier",
            short_title="MOD",
        )
        self.stage = factories.StageFactory.create(
            division=self.division,
            title="Quarter Finals Stage",
            short_title="QF",
        )
        self.season.competition.title = "International Touch Championship"
        self.season.competition.short_title = "ITC"
        self.season.competition.save()

        self.ground = factories.GroundFactory.create(venue__season=self.season)
        self.match = factories.MatchFactory.create(
            stage=self.stage,
            play_at=self.ground,
            label="QF1",
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
            date=date(2025, 5, 1),
            time=time(14, 0),
        )

    def test_long_form_uses_titles(self):
        body = build_live_stream_body(self.match)
        title = body["snippet"]["title"]
        self.assertIn("Mens Open Division Premier Tier", title)
        self.assertIn("International Touch Championship", title)
        self.assertIn("Premiership Season Two Thousand Twenty Five", title)

    def test_short_form_uses_short_titles(self):
        body = build_live_stream_body(self.match, short=True)
        title = body["snippet"]["title"]
        self.assertIn("MOD", title)
        self.assertIn("ITC", title)
        self.assertIn("PS25", title)
        self.assertNotIn("Mens Open Division Premier Tier", title)
        self.assertNotIn("International Touch Championship", title)

    def test_short_form_falls_back_to_title_when_unset(self):
        self.division.short_title = ""
        self.division.save()
        body = build_live_stream_body(self.match, short=True)
        title = body["snippet"]["title"]
        self.assertIn("Mens Open Division Premier Tier", title)

    def test_short_form_substitutes_in_title_attribute_access(self):
        """``{{ division.title }}`` should also receive the short form."""
        wrapped = _ShortTitle(self.division)
        rendered = Template("{{ d }}|{{ d.title }}|{{ d.slug }}").render(
            Context({"d": wrapped})
        )
        self.assertEqual(
            "MOD|MOD|" + self.division.slug,
            rendered,
        )


class SyncLiveStreamTaskTests(TestCase):
    """Exercise the celery task that synchronises a match with YouTube."""

    def setUp(self):
        self.season = factories.SeasonFactory.create(
            title="Long Season Title For Live Streaming Tests",
            short_title="LS25",
            live_stream=True,
            live_stream_project_id="test-project",
            live_stream_client_id="test-client-id",
            live_stream_client_secret="test-client-secret",
            live_stream_privacy="unlisted",
        )
        self.division = factories.DivisionFactory.create(
            season=self.season,
            title="Mens Premier Open Division Top Tier Premier",
            short_title="MPO",
        )
        self.stage = factories.StageFactory.create(
            division=self.division,
            title="Group Stage One",
            short_title="GS1",
        )
        self.ground = factories.GroundFactory.create(
            venue__season=self.season,
            external_identifier=None,
        )
        self.match = factories.MatchFactory.create(
            stage=self.stage,
            play_at=self.ground,
            label="Round 1",
            live_stream=True,
            external_identifier=None,
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
            date=date(2025, 5, 1),
            time=time(14, 0),
        )

    @mock.patch("tournamentcontrol.competition.tasks.set_youtube_thumbnail")
    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_insert_creates_broadcast_and_persists_identifier(
        self, mock_youtube_prop, mock_thumbnail
    ):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        mock_youtube.liveBroadcasts.return_value.insert.return_value.execute.return_value = {
            "id": "yt-broadcast-new",
        }

        sync_live_stream(self.match.pk)

        self.match.refresh_from_db()
        self.assertEqual("yt-broadcast-new", self.match.external_identifier)
        self.assertEqual(["https://youtu.be/yt-broadcast-new"], self.match.videos)
        mock_youtube.liveBroadcasts.return_value.insert.assert_called_once()

    @mock.patch("tournamentcontrol.competition.tasks.set_youtube_thumbnail")
    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_retries_with_short_titles_when_title_too_long(
        self, mock_youtube_prop, mock_thumbnail
    ):
        """A title-length HttpError triggers a retry using ``short_title``."""
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        mock_youtube.liveBroadcasts.return_value.insert.return_value.execute.side_effect = [
            _http_error(400, "title is too long"),
            {"id": "yt-broadcast-short"},
        ]

        sync_live_stream(self.match.pk)

        self.match.refresh_from_db()
        self.assertEqual("yt-broadcast-short", self.match.external_identifier)

        insert_calls = mock_youtube.liveBroadcasts.return_value.insert.call_args_list
        self.assertEqual(2, len(insert_calls))
        first_title = insert_calls[0].kwargs["body"]["snippet"]["title"]
        retry_title = insert_calls[1].kwargs["body"]["snippet"]["title"]
        self.assertIn("Mens Premier Open Division Top Tier Premier", first_title)
        self.assertIn("MPO", retry_title)
        self.assertIn("LS25", retry_title)
        self.assertNotIn(
            "Mens Premier Open Division Top Tier Premier", retry_title
        )

    @mock.patch("tournamentcontrol.competition.tasks.set_youtube_thumbnail")
    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_unrelated_http_error_is_propagated_without_retry(
        self, mock_youtube_prop, mock_thumbnail
    ):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        mock_youtube.liveBroadcasts.return_value.insert.return_value.execute.side_effect = (
            _http_error(403, "quotaExceeded")
        )

        with self.assertRaises(HttpError):
            sync_live_stream(self.match.pk)

        self.assertEqual(
            1,
            len(mock_youtube.liveBroadcasts.return_value.insert.call_args_list),
        )

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_no_credentials_skips_api(self, mock_youtube_prop):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        self.season.live_stream_client_id = None
        self.season.live_stream_client_secret = None
        self.season.save()

        sync_live_stream(self.match.pk)

        mock_youtube.liveBroadcasts.assert_not_called()

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_returns_quietly_when_match_was_deleted(self, mock_youtube_prop):
        """A worker picking up a task for a deleted match must not raise."""
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        match_pk = self.match.pk
        self.match.delete()

        sync_live_stream(match_pk)

        mock_youtube_prop.assert_not_called()
        mock_youtube.liveBroadcasts.assert_not_called()

    @mock.patch("tournamentcontrol.competition.tasks.set_youtube_thumbnail")
    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_delete_clears_external_identifier_when_disabling(
        self, mock_youtube_prop, mock_thumbnail
    ):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        mock_youtube.liveBroadcasts.return_value.delete.return_value.execute.return_value = {}

        self.match.external_identifier = "yt-existing"
        self.match.live_stream = False
        self.match.videos = ["https://youtu.be/yt-existing"]
        self.match.live_stream_bind = "stale-bound-stream"
        self.match.save()

        sync_live_stream(self.match.pk)

        self.match.refresh_from_db()
        self.assertEqual(None, self.match.external_identifier)
        self.assertEqual(None, self.match.videos)
        self.assertEqual(None, self.match.live_stream_bind)
        mock_youtube.liveBroadcasts.return_value.delete.assert_called_once_with(
            id="yt-existing"
        )

    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_no_op_returns_without_calling_api(self, mock_youtube_prop):
        """No external broadcast and live_stream=False should be a fast no-op."""
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        self.match.live_stream = False
        self.match.external_identifier = None
        self.match.save()

        sync_live_stream(self.match.pk)

        mock_youtube.liveBroadcasts.assert_not_called()
        # The youtube property shouldn't be resolved at all in the no-op path.
        self.assertEqual(0, mock_youtube_prop.call_count)

    @mock.patch("tournamentcontrol.competition.tasks.set_youtube_thumbnail")
    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_delete_runs_when_schedule_was_cleared(
        self, mock_youtube_prop, mock_thumbnail
    ):
        """Disabling live_stream still deletes even if the schedule was cleared."""
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        mock_youtube.liveBroadcasts.return_value.delete.return_value.execute.return_value = {}

        self.match.external_identifier = "yt-orphan"
        self.match.live_stream = False
        self.match.videos = ["https://youtu.be/yt-orphan"]
        self.match.datetime = None
        self.match.date = None
        self.match.time = None
        self.match.save()

        sync_live_stream(self.match.pk)

        self.match.refresh_from_db()
        self.assertEqual(None, self.match.external_identifier)
        mock_youtube.liveBroadcasts.return_value.delete.assert_called_once_with(
            id="yt-orphan"
        )

    @mock.patch("tournamentcontrol.competition.tasks.set_youtube_thumbnail")
    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_youtube_client_is_cached_within_apply_sync(
        self, mock_youtube_prop, mock_thumbnail
    ):
        """``season.youtube`` should be resolved once per sync, not per call."""
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        mock_youtube.liveBroadcasts.return_value.insert.return_value.execute.return_value = {
            "id": "yt-broadcast-cached",
        }
        mock_youtube.liveBroadcasts.return_value.bind.return_value.execute.return_value = {
            "contentDetails": {"boundStreamId": "stream-resource-cached"},
        }

        self.ground.external_identifier = "stream-resource-cached"
        self.ground.save()

        sync_live_stream(self.match.pk)

        self.assertEqual(1, mock_youtube_prop.call_count)

    @mock.patch("tournamentcontrol.competition.tasks.set_youtube_thumbnail")
    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_update_calls_youtube_and_schedules_thumbnail(
        self, mock_youtube_prop, mock_thumbnail
    ):
        """An existing broadcast is updated and the thumbnail task is scheduled."""
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        mock_youtube.liveBroadcasts.return_value.update.return_value.execute.return_value = {
            "id": "yt-existing-update",
        }

        self.match.external_identifier = "yt-existing-update"
        self.match.live_stream = True
        self.match.save()

        sync_live_stream(self.match.pk)

        update_call = mock_youtube.liveBroadcasts.return_value.update.call_args
        self.assertEqual(
            "snippet,status,contentDetails", update_call.kwargs["part"]
        )
        self.assertEqual(
            "yt-existing-update", update_call.kwargs["body"]["id"]
        )
        mock_youtube.liveBroadcasts.return_value.insert.assert_not_called()
        mock_thumbnail.s.assert_called_once_with(self.match.pk)
        mock_thumbnail.s.return_value.apply_async.assert_called_once_with(
            countdown=10
        )

    @mock.patch("tournamentcontrol.competition.tasks.set_youtube_thumbnail")
    @mock.patch(
        "tournamentcontrol.competition.models.Season.youtube",
        new_callable=mock.PropertyMock,
    )
    def test_bind_persists_bound_stream_id_when_ground_has_external_id(
        self, mock_youtube_prop, mock_thumbnail
    ):
        mock_youtube = mock.MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        mock_youtube.liveBroadcasts.return_value.insert.return_value.execute.return_value = {
            "id": "yt-broadcast-bind",
        }
        mock_youtube.liveBroadcasts.return_value.bind.return_value.execute.return_value = {
            "contentDetails": {"boundStreamId": "stream-resource-1"},
        }

        self.ground.external_identifier = "stream-resource-1"
        self.ground.save()

        sync_live_stream(self.match.pk)

        self.match.refresh_from_db()
        self.assertEqual("stream-resource-1", self.match.live_stream_bind)
