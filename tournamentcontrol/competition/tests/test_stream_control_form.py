import unittest
from unittest import mock

from test_plus import TestCase

from tournamentcontrol.competition.forms import StreamControlForm
from tournamentcontrol.competition.tests import factories


class StreamControlFormTests(TestCase):
    """
    Test StreamControlForm functionality with YouTube token refresh.

    This ensures the form works correctly with the improved YouTube token refresh
    implementation in the Season model.
    """

    def setUp(self):
        """Create a season with YouTube configuration and matches for testing."""
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
                "https://www.googleapis.com/auth/youtube.readonly",
                "https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtubepartner",
            ],
        )

        # Create matches with external identifiers for YouTube streaming
        self.stage = factories.StageFactory.create(division__season=self.season)
        self.match1 = factories.MatchFactory.create(
            stage=self.stage,
            external_identifier="yt_id_1",
            live_stream=True,
        )
        self.match2 = factories.MatchFactory.create(
            stage=self.stage,
            external_identifier="yt_id_2",
            live_stream=True,
        )

    def test_form_with_valid_data(self):
        """Test that StreamControlForm validates correctly with valid data."""
        form = StreamControlForm(data={"status": "live"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["status"], "live")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_form_save_with_youtube_service(self, mock_build):
        """Test that the form's save method works with YouTube service from Season."""
        # Create a mock YouTube service
        mock_youtube = mock.Mock()
        mock_youtube.liveBroadcasts.return_value.transition.return_value.execute.return_value = (
            {}
        )
        mock_build.return_value = mock_youtube

        # Create form with valid data
        form = StreamControlForm(data={"status": "live"})
        self.assertTrue(form.is_valid())

        # Mock request object
        mock_request = mock.Mock()
        mock_request.META = {}

        # Create queryset of matches
        queryset = [self.match1, self.match2]

        # Call save method - this should not raise RefreshError
        # because our improved youtube property handles token refresh
        form.save(mock_request, self.season.youtube, queryset)

        # Verify YouTube API was called for each match
        self.assertEqual(
            mock_youtube.liveBroadcasts.return_value.transition.call_count, 2
        )

        # Verify the calls were made with correct parameters
        calls = mock_youtube.liveBroadcasts.return_value.transition.call_args_list
        for i, call in enumerate(calls):
            args, kwargs = call
            expected_match = queryset[i]
            self.assertEqual(kwargs["broadcastStatus"], "live")
            self.assertEqual(kwargs["id"], expected_match.external_identifier)
            self.assertEqual(kwargs["part"], "snippet,status")

    @mock.patch("tournamentcontrol.competition.models.build")
    @mock.patch("tournamentcontrol.competition.models.Request")
    def test_form_save_with_token_refresh(self, mock_request_class, mock_build):
        """Test that form save works when YouTube tokens need refreshing."""
        from google.oauth2.credentials import Credentials

        # Create mock credentials that are expired but can be refreshed
        mock_credentials = mock.Mock(spec=Credentials)
        mock_credentials.expired = True
        mock_credentials.refresh_token = "refresh-token-789"
        mock_credentials.token = "new-access-token"

        def mock_refresh(request):
            mock_credentials.token = "new-access-token"

        mock_credentials.refresh.side_effect = mock_refresh

        # Create mock YouTube service
        mock_youtube = mock.Mock()
        mock_youtube.liveBroadcasts.return_value.transition.return_value.execute.return_value = (
            {}
        )
        mock_build.return_value = mock_youtube

        # Mock the Credentials constructor to return expired credentials
        with mock.patch(
            "tournamentcontrol.competition.models.Credentials",
            return_value=mock_credentials,
        ):
            # Create form and save
            form = StreamControlForm(data={"status": "testing"})
            self.assertTrue(form.is_valid())

            mock_request = mock.Mock()
            mock_request.META = {}
            queryset = [self.match1]

            # This should work without error - token refresh should happen automatically
            form.save(mock_request, self.season.youtube, queryset)

            # Verify token was refreshed
            mock_credentials.refresh.assert_called_once()

            # Verify season token was updated
            self.season.refresh_from_db()
            self.assertEqual(self.season.live_stream_token, "new-access-token")

            # Verify YouTube API was still called successfully
            mock_youtube.liveBroadcasts.return_value.transition.assert_called_once()
