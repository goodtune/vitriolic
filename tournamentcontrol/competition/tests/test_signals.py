from unittest import mock
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings

from tournamentcontrol.competition.models import LadderEntry, LadderSummary
from tournamentcontrol.competition.tests import factories


class SignalHandlerTests(TestCase):
    def test_ladder_entry_match_no_score(self):
        factories.MatchFactory.create()
        self.assertQuerySetEqual(LadderEntry.objects.all(), LadderEntry.objects.none())

    def test_ladder_entry_match_with_score(self):
        factories.MatchFactory.create(home_team_score=5, away_team_score=2)
        self.assertCountEqual(
            [
                (1, 0, 0, 5, 2, 3, 3),
                (0, 1, 0, 2, 5, -3, 3),
            ],
            LadderEntry.objects.values_list(
                "win", "loss", "draw", "score_for", "score_against", "diff", "margin"
            ),
        )

    def test_ladder_summary_3_match_series(self):
        # seed a match which will produce all required relations
        match = factories.MatchFactory.create(home_team_score=5, away_team_score=2)

        # build two more matches with known results to produce LadderSummary
        factories.MatchFactory.create(
            home_team=match.home_team,
            home_team_score=3,
            away_team=match.away_team,
            away_team_score=4,
            stage=match.stage,
        )
        factories.MatchFactory.create(
            home_team=match.home_team,
            home_team_score=2,
            away_team=match.away_team,
            away_team_score=2,
            stage=match.stage,
        )

        self.assertCountEqual(
            [
                (3, 1, 1, 1, 10, 8, 2),
                (3, 1, 1, 1, 8, 10, -2),
            ],
            LadderSummary.objects.values_list(
                "played",
                "win",
                "loss",
                "draw",
                "score_for",
                "score_against",
                "difference",
            ),
        )


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class YouTubeSignalHandlerTests(TestCase):
    def setUp(self):
        """Set up test fixtures for YouTube signal handler tests."""
        self.season_with_credentials = factories.SeasonFactory.create(
            live_stream=True,
            live_stream_client_id="test-client-id",
            live_stream_client_secret="test-client-secret",
            live_stream_token="test-token",
            live_stream_refresh_token="test-refresh-token",
            live_stream_token_uri="https://oauth2.googleapis.com/token",
            live_stream_scopes=["https://www.googleapis.com/auth/youtube"]
        )
        self.season_no_credentials = factories.SeasonFactory.create(
            live_stream=True,
            live_stream_client_id=None,
            live_stream_client_secret=None,
        )
        self.stage_with_creds = factories.StageFactory.create(
            division__season=self.season_with_credentials
        )
        self.stage_no_creds = factories.StageFactory.create(
            division__season=self.season_no_credentials
        )

    @patch('tournamentcontrol.competition.tasks.set_youtube_thumbnail')
    @patch('tournamentcontrol.competition.models.Season.youtube')
    def test_match_youtube_sync_guard_clause_no_credentials(self, mock_youtube, mock_thumbnail_task):
        """
        Test that the signal handler guard clause prevents YouTube API calls when
        no credentials are configured.
        """
        # Create a match with live streaming enabled but no YouTube credentials
        match = factories.MatchFactory.create(
            stage=self.stage_no_creds,
            live_stream=True,
            external_identifier=None,
        )

        # Save the match (which triggers the signal)
        match.save()

        # Verify YouTube API was not called due to guard clause
        mock_youtube.assert_not_called()
        mock_thumbnail_task.s.assert_not_called()

    @patch('tournamentcontrol.competition.tasks.set_youtube_thumbnail')
    @patch('tournamentcontrol.competition.models.Season.youtube')
    def test_match_youtube_sync_creates_broadcast_new_live_stream(self, mock_youtube, mock_thumbnail_task):
        """
        Test that enabling live streaming on a match without external_identifier
        creates a new YouTube broadcast.
        """
        # Mock the YouTube API response for broadcast creation
        mock_broadcast = {"id": "test-broadcast-id"}
        mock_broadcasts = MagicMock()
        mock_broadcasts.insert.return_value.execute.return_value = mock_broadcast
        mock_youtube.return_value.liveBroadcasts.return_value = mock_broadcasts

        # Create a match with live streaming enabled but no external identifier
        match = factories.MatchFactory.create(
            stage=self.stage_with_creds,
            live_stream=True,
            external_identifier=None,
        )

        # Save the match (which triggers the signal)
        match.save()

        # Verify YouTube broadcast was created
        mock_broadcasts.insert.assert_called_once()
        call_args = mock_broadcasts.insert.call_args
        self.assertEqual(call_args[1]['part'], 'id,snippet,status,contentDetails')
        
        # Verify external_identifier was set
        match.refresh_from_db()
        self.assertEqual(match.external_identifier, 'test-broadcast-id')
        
        # Verify video link was added
        self.assertIn('https://youtu.be/test-broadcast-id', match.videos)
        
        # Verify thumbnail task was queued
        mock_thumbnail_task.s.assert_called_once_with(match.pk)

    @patch('tournamentcontrol.competition.tasks.set_youtube_thumbnail')
    @patch('tournamentcontrol.competition.models.Season.youtube')
    def test_match_youtube_sync_updates_existing_broadcast(self, mock_youtube, mock_thumbnail_task):
        """
        Test that updating a match with existing external_identifier updates
        the YouTube broadcast.
        """
        # Mock the YouTube API response for broadcast update
        mock_broadcast = {"id": "existing-broadcast-id"}
        mock_broadcasts = MagicMock()
        mock_broadcasts.update.return_value.execute.return_value = mock_broadcast
        mock_youtube.return_value.liveBroadcasts.return_value = mock_broadcasts

        # Create a match with live streaming and existing external identifier
        match = factories.MatchFactory.create(
            stage=self.stage_with_creds,
            live_stream=True,
            external_identifier='existing-broadcast-id',
        )

        # Save the match (which triggers the signal)
        match.save()

        # Verify YouTube broadcast was updated
        mock_broadcasts.update.assert_called_once()
        call_args = mock_broadcasts.update.call_args
        self.assertEqual(call_args[1]['part'], 'snippet,status,contentDetails')
        self.assertEqual(call_args[1]['body']['id'], 'existing-broadcast-id')
        
        # Verify thumbnail task was queued
        mock_thumbnail_task.s.assert_called_once_with(match.pk)

    @patch('tournamentcontrol.competition.tasks.set_youtube_thumbnail')
    @patch('tournamentcontrol.competition.models.Season.youtube')
    def test_match_youtube_sync_deletes_broadcast_disable_streaming(self, mock_youtube, mock_thumbnail_task):
        """
        Test that disabling live streaming on a match with external_identifier
        deletes the YouTube broadcast.
        """
        # Mock the YouTube API response for broadcast deletion
        mock_broadcasts = MagicMock()
        mock_broadcasts.delete.return_value.execute.return_value = {}
        mock_youtube.return_value.liveBroadcasts.return_value = mock_broadcasts

        # Create a match without triggering the signal first
        video_id = 'test-video-to-delete'
        with mock.patch('tournamentcontrol.competition.signals.matches.match_youtube_sync'):
            # Bypass signal during creation to set up test state
            match = factories.MatchFactory.create(
                stage=self.stage_with_creds,
                live_stream=True,  # Initially enabled
                external_identifier=video_id,
                videos=[f'https://youtu.be/{video_id}', 'https://example.com/other-video'],
            )

        # Now disable live streaming and save (which triggers the signal we want to test)
        match.live_stream = False
        match.save()

        # Verify YouTube broadcast was deleted
        mock_broadcasts.delete.assert_called_once_with(id=video_id)
        
        # Verify external_identifier was cleared and video link removed
        match.refresh_from_db()
        self.assertIsNone(match.external_identifier)
        self.assertNotIn(f'https://youtu.be/{video_id}', match.videos or [])
        
        # Verify other videos were preserved
        self.assertIn('https://example.com/other-video', match.videos)
        
        # Verify thumbnail task was not queued for deletion
        mock_thumbnail_task.s.assert_not_called()

    @patch('tournamentcontrol.competition.tasks.set_youtube_thumbnail')
    @patch('tournamentcontrol.competition.models.Season.youtube')
    def test_match_youtube_sync_clears_videos_when_empty(self, mock_youtube, mock_thumbnail_task):
        """
        Test that disabling live streaming clears the videos field when no other videos remain.
        """
        # Mock the YouTube API response for broadcast deletion
        mock_broadcasts = MagicMock()
        mock_broadcasts.delete.return_value.execute.return_value = {}
        mock_youtube.return_value.liveBroadcasts.return_value = mock_broadcasts

        # Create a match without triggering the signal first
        video_id = 'only-video-to-delete'
        with mock.patch('tournamentcontrol.competition.signals.matches.match_youtube_sync'):
            # Bypass signal during creation to set up test state
            match = factories.MatchFactory.create(
                stage=self.stage_with_creds,
                live_stream=True,  # Initially enabled
                external_identifier=video_id,
                videos=[f'https://youtu.be/{video_id}'],  # Only YouTube video
            )

        # Now disable live streaming and save (which triggers the signal)
        match.live_stream = False
        match.save()

        # Verify external_identifier was cleared and videos field is None
        match.refresh_from_db()
        self.assertIsNone(match.external_identifier)
        self.assertIsNone(match.videos)

    @patch('tournamentcontrol.competition.tasks.set_youtube_thumbnail')
    @patch('tournamentcontrol.competition.models.Season.youtube')
    def test_match_youtube_sync_no_action_no_live_stream_no_external_id(self, mock_youtube, mock_thumbnail_task):
        """
        Test that matches without live streaming and no external identifier
        don't trigger any YouTube API calls.
        """
        # Create a regular match with no live streaming
        match = factories.MatchFactory.create(
            stage=self.stage_with_creds,
            live_stream=False,
            external_identifier=None,
        )

        # Save the match (which triggers the signal)
        match.save()

        # Verify no YouTube API calls were made
        mock_youtube.return_value.liveBroadcasts.assert_not_called()
        mock_thumbnail_task.s.assert_not_called()

    @patch('tournamentcontrol.competition.tasks.set_youtube_thumbnail')
    @patch('tournamentcontrol.competition.models.Season.youtube')  
    def test_match_youtube_sync_broadcast_title_with_label(self, mock_youtube, mock_thumbnail_task):
        """
        Test that the broadcast title includes match label when available.
        """
        # Mock the YouTube API response
        mock_broadcast = {"id": "test-broadcast-id"}
        mock_broadcasts = MagicMock()
        mock_broadcasts.insert.return_value.execute.return_value = mock_broadcast
        mock_youtube.return_value.liveBroadcasts.return_value = mock_broadcasts

        # Create teams with specific names
        home_team = factories.TeamFactory.create(title="Home Tigers")
        away_team = factories.TeamFactory.create(title="Away Lions")
        
        # Create a match with a label
        match = factories.MatchFactory.create(
            stage=self.stage_with_creds,
            live_stream=True,
            external_identifier=None,
            label="Grand Final",
            home_team=home_team,
            away_team=away_team,
        )

        # Save the match (which triggers the signal)
        match.save()

        # Verify the broadcast title includes the label
        call_args = mock_broadcasts.insert.call_args
        body = call_args[1]['body']
        title = body['snippet']['title']
        self.assertIn('Grand Final', title)
        self.assertIn('Home Tigers', title)
        self.assertIn('Away Lions', title)

    @patch('tournamentcontrol.competition.tasks.set_youtube_thumbnail')
    @patch('tournamentcontrol.competition.models.Season.youtube')
    def test_match_youtube_sync_broadcast_title_without_label(self, mock_youtube, mock_thumbnail_task):
        """
        Test that the broadcast title works correctly when no label is provided.
        """
        # Mock the YouTube API response
        mock_broadcast = {"id": "test-broadcast-id"}
        mock_broadcasts = MagicMock()
        mock_broadcasts.insert.return_value.execute.return_value = mock_broadcast
        mock_youtube.return_value.liveBroadcasts.return_value = mock_broadcasts

        # Create teams with specific names
        home_team = factories.TeamFactory.create(title="Home Eagles")
        away_team = factories.TeamFactory.create(title="Away Hawks")
        
        # Create a match without a label
        match = factories.MatchFactory.create(
            stage=self.stage_with_creds,
            live_stream=True,
            external_identifier=None,
            label=None,  # No label
            home_team=home_team,
            away_team=away_team,
        )

        # Save the match (which triggers the signal)
        match.save()

        # Verify the broadcast title doesn't include a label but has team names
        call_args = mock_broadcasts.insert.call_args
        body = call_args[1]['body']
        title = body['snippet']['title']
        self.assertNotIn('Grand Final', title)  # No label
        self.assertIn('Home Eagles', title)
        self.assertIn('Away Hawks', title)
