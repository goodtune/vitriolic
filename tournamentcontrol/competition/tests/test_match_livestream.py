"""
Test live streaming functionality on Match model.
"""

import warnings
from unittest import mock

from googleapiclient.errors import HttpError
from test_plus import TestCase

from tournamentcontrol.competition.exceptions import (
    LiveStreamIdentifierMissing,
    InvalidLiveStreamTransition,
    LiveStreamTransitionWarning,
)
from tournamentcontrol.competition.tests import factories


class MatchLiveStreamTests(TestCase):
    """Test Match.transition_live_stream method."""

    def setUp(self):
        """Create test fixtures with YouTube configuration."""
        self.season = factories.SeasonFactory.create(
            live_stream=True,
            live_stream_project_id="test-project-123",
            live_stream_client_id="test-client-123.apps.googleusercontent.com",
            live_stream_client_secret="test-secret-456",
            live_stream_token="current-access-token",
            live_stream_refresh_token="refresh-token-789",
            live_stream_token_uri="https://oauth2.googleapis.com/token",
            live_stream_scopes=[
                "https://www.googleapis.com/auth/youtube",
                "https://www.googleapis.com/auth/youtube.force-ssl",
            ],
        )
        
        self.stage = factories.StageFactory.create(division__season=self.season)
        
        # Match with live stream identifier
        self.match_with_stream = factories.MatchFactory.create(
            stage=self.stage,
            external_identifier="yt_broadcast_123",
            live_stream=True,
        )
        
        # Match without live stream identifier
        self.match_without_stream = factories.MatchFactory.create(
            stage=self.stage,
            external_identifier=None,
            live_stream=False,
        )

    def test_transition_without_identifier_raises_exception(self):
        """Test that transition raises LiveStreamIdentifierMissing when no external_identifier."""
        with self.assertRaises(LiveStreamIdentifierMissing) as cm:
            self.match_without_stream.transition_live_stream('testing')
        
        self.assertIn('does not have a live stream identifier', str(cm.exception))
        self.assertIn(str(self.match_without_stream), str(cm.exception))

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_successful_transition(self, mock_build):
        """Test successful live stream transition."""
        # Mock YouTube service
        mock_youtube = mock.Mock()
        mock_response = {'id': 'yt_broadcast_123', 'status': 'live'}
        mock_youtube.liveBroadcasts.return_value.transition.return_value.execute.return_value = mock_response
        mock_build.return_value = mock_youtube
        
        # Make transition
        response = self.match_with_stream.transition_live_stream('live')
        
        # Verify response
        self.assertEqual(response, mock_response)
        
        # Verify YouTube API was called correctly
        mock_youtube.liveBroadcasts.return_value.transition.assert_called_once_with(
            broadcastStatus='live',
            id='yt_broadcast_123',
            part='snippet,status'
        )

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_transition_with_custom_youtube_service(self, mock_build):
        """Test transition with provided YouTube service instead of season's."""
        # Create custom mock service
        custom_youtube = mock.Mock()
        custom_response = {'custom': 'response'}
        custom_youtube.liveBroadcasts.return_value.transition.return_value.execute.return_value = custom_response
        
        # The build mock should not be called when providing custom service
        response = self.match_with_stream.transition_live_stream('testing', custom_youtube)
        
        # Verify custom service was used
        self.assertEqual(response, custom_response)
        custom_youtube.liveBroadcasts.return_value.transition.assert_called_once()
        
        # Verify season's YouTube service was not created
        mock_build.assert_not_called()

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_invalid_transition_from_complete_status(self, mock_build):
        """Test that transitions from 'complete' status raise InvalidLiveStreamTransition."""
        # Mock YouTube service to return 'complete' status
        mock_youtube = mock.Mock()
        mock_list_response = {
            'items': [{'status': {'lifeCycleStatus': 'complete'}}]
        }
        mock_youtube.liveBroadcasts.return_value.list.return_value.execute.return_value = mock_list_response
        mock_build.return_value = mock_youtube
        
        with self.assertRaises(InvalidLiveStreamTransition) as cm:
            self.match_with_stream.transition_live_stream('testing', mock_youtube)
        
        self.assertIn("Cannot transition from 'complete' to 'testing'", str(cm.exception))

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_potentially_invalid_transition_issues_warning(self, mock_build):
        """Test that potentially invalid transitions issue warnings."""
        # Mock YouTube service to return 'live' status
        mock_youtube = mock.Mock()
        mock_list_response = {
            'items': [{'status': {'lifeCycleStatus': 'live'}}]
        }
        mock_youtube.liveBroadcasts.return_value.list.return_value.execute.return_value = mock_list_response
        
        # Mock successful transition response
        mock_transition_response = {'status': 'testing'}
        mock_youtube.liveBroadcasts.return_value.transition.return_value.execute.return_value = mock_transition_response
        mock_build.return_value = mock_youtube
        
        # Capture warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            response = self.match_with_stream.transition_live_stream('testing', mock_youtube)
            
            # Verify warning was issued
            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, LiveStreamTransitionWarning))
            self.assertIn("Potentially invalid transition from 'live' to 'testing'", str(w[0].message))
            
            # Verify transition still proceeded
            self.assertEqual(response, mock_transition_response)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_transition_with_youtube_api_exception_handling(self, mock_build):
        """Test that YouTube API exceptions are propagated properly."""
        
        # Mock YouTube service to raise HttpError
        mock_youtube = mock.Mock()
        mock_youtube.liveBroadcasts.return_value.transition.return_value.execute.side_effect = HttpError(
            resp=mock.Mock(status=400), content=b'{"error": {"message": "Invalid broadcast ID"}}'
        )
        mock_build.return_value = mock_youtube
        
        # Verify HttpError is propagated
        with self.assertRaises(HttpError):
            self.match_with_stream.transition_live_stream('live', mock_youtube)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_valid_transition_sequences(self, mock_build):
        """Test that valid transition sequences work without warnings."""
        mock_youtube = mock.Mock()
        mock_build.return_value = mock_youtube
        
        # Test testing -> live (valid)
        mock_youtube.liveBroadcasts.return_value.list.return_value.execute.return_value = {
            'items': [{'status': {'lifeCycleStatus': 'testing'}}]
        }
        mock_youtube.liveBroadcasts.return_value.transition.return_value.execute.return_value = {'status': 'live'}
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            response = self.match_with_stream.transition_live_stream('live', mock_youtube)
            
            # Should be no warnings for valid transition
            self.assertEqual(len(w), 0)
            self.assertEqual(response['status'], 'live')

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_same_status_transition_allowed(self, mock_build):
        """Test that transitioning to the same status is allowed without warning."""
        mock_youtube = mock.Mock()
        mock_build.return_value = mock_youtube
        
        # Mock current status as 'testing'
        mock_youtube.liveBroadcasts.return_value.list.return_value.execute.return_value = {
            'items': [{'status': {'lifeCycleStatus': 'testing'}}]
        }
        mock_youtube.liveBroadcasts.return_value.transition.return_value.execute.return_value = {'status': 'testing'}
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            response = self.match_with_stream.transition_live_stream('testing', mock_youtube)
            
            # Should be no warnings for same-status transition
            self.assertEqual(len(w), 0)
            self.assertEqual(response['status'], 'testing')

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_transition_when_status_check_fails(self, mock_build):
        """Test transition proceeds when status check fails."""
        mock_youtube = mock.Mock()
        mock_build.return_value = mock_youtube
        
        # Mock status check to raise exception
        mock_youtube.liveBroadcasts.return_value.list.return_value.execute.side_effect = Exception("API Error")
        
        # Mock successful transition
        mock_youtube.liveBroadcasts.return_value.transition.return_value.execute.return_value = {'status': 'live'}
        
        # Should proceed despite status check failure
        response = self.match_with_stream.transition_live_stream('live', mock_youtube)
        
        self.assertEqual(response['status'], 'live')
        mock_youtube.liveBroadcasts.return_value.transition.assert_called_once_with(
            broadcastStatus='live',
            id='yt_broadcast_123',
            part='snippet,status'
        )