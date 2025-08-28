import unittest
from datetime import datetime, timedelta
from unittest import mock

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from test_plus import TestCase

from tournamentcontrol.competition.tests import factories


class YouTubeTokenRefreshTests(TestCase):
    """
    Test YouTube OAuth token refresh functionality in Season model.

    This addresses the issue where expired YouTube OAuth tokens cause
    RefreshError in stream control functionality.
    """

    def setUp(self):
        """Create a season with YouTube live streaming configuration."""
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

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_youtube_property_creates_service_with_credentials(self, mock_build):
        """Test that the youtube property creates a service with proper credentials."""
        # Access the youtube property
        youtube_service = self.season.youtube

        # Verify build was called with correct parameters
        mock_build.assert_called_once_with("youtube", "v3", credentials=mock.ANY)

        # Check the credentials passed to build
        call_args = mock_build.call_args
        credentials = call_args[1]["credentials"]

        self.assertIsInstance(credentials, Credentials)
        self.assertEqual(credentials.client_id, self.season.live_stream_client_id)
        self.assertEqual(
            credentials.client_secret, self.season.live_stream_client_secret
        )
        self.assertEqual(credentials.token, self.season.live_stream_token)
        self.assertEqual(
            credentials.refresh_token, self.season.live_stream_refresh_token
        )

    @mock.patch("tournamentcontrol.competition.models.build")
    @mock.patch("tournamentcontrol.competition.models.Request")
    def test_youtube_property_refreshes_expired_tokens(
        self, mock_request_class, mock_build
    ):
        """Test that expired tokens are automatically refreshed."""
        # Create a mock credentials object that starts expired
        mock_credentials = mock.Mock(spec=Credentials)
        mock_credentials.expired = True
        mock_credentials.refresh_token = "refresh-token-789"
        mock_credentials.token = "new-access-token"

        # Mock the successful refresh
        def mock_refresh(request):
            mock_credentials.token = "new-access-token"

        mock_credentials.refresh.side_effect = mock_refresh

        # Mock the Credentials constructor
        with mock.patch(
            "tournamentcontrol.competition.models.Credentials",
            return_value=mock_credentials,
        ):
            # Access the youtube property
            youtube_service = self.season.youtube

            # Verify refresh was called
            mock_credentials.refresh.assert_called_once_with(
                mock_request_class.return_value
            )

            # Verify the season's token was updated
            self.season.refresh_from_db()
            self.assertEqual(self.season.live_stream_token, "new-access-token")

            # Verify build was called with refreshed credentials
            mock_build.assert_called_once_with(
                "youtube", "v3", credentials=mock_credentials
            )

    @mock.patch("tournamentcontrol.competition.models.build")
    @mock.patch("tournamentcontrol.competition.models.Request")
    @mock.patch("tournamentcontrol.competition.models.logger")
    def test_youtube_property_handles_refresh_failure(
        self, mock_logger, mock_request_class, mock_build
    ):
        """Test that refresh failures are properly handled and logged."""
        # Create a mock credentials object that is expired
        mock_credentials = mock.Mock(spec=Credentials)
        mock_credentials.expired = True
        mock_credentials.refresh_token = "refresh-token-789"
        mock_credentials.refresh.side_effect = RefreshError(
            "Token has been expired or revoked."
        )

        # Mock the Credentials constructor
        with mock.patch(
            "tournamentcontrol.competition.models.Credentials",
            return_value=mock_credentials,
        ):
            # Accessing the youtube property should raise RefreshError
            with self.assertRaises(RefreshError):
                youtube_service = self.season.youtube

            # Verify the error was logged
            mock_logger.error.assert_called_once()

            # Verify the season's token wasn't changed
            self.season.refresh_from_db()
            self.assertEqual(self.season.live_stream_token, "current-access-token")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_youtube_property_with_valid_unexpired_tokens(self, mock_build):
        """Test that valid, unexpired tokens don't trigger refresh."""
        # Create a mock credentials object that is not expired
        mock_credentials = mock.Mock(spec=Credentials)
        mock_credentials.expired = False
        mock_credentials.refresh_token = "refresh-token-789"

        # Mock the Credentials constructor
        with mock.patch(
            "tournamentcontrol.competition.models.Credentials",
            return_value=mock_credentials,
        ):
            # Access the youtube property
            youtube_service = self.season.youtube

            # Verify refresh was NOT called
            mock_credentials.refresh.assert_not_called()

            # Verify build was called with the credentials
            mock_build.assert_called_once_with(
                "youtube", "v3", credentials=mock_credentials
            )

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_youtube_property_without_refresh_token(self, mock_build):
        """Test behavior when credentials are expired but no refresh token available."""
        # Create a mock credentials object that is expired but has no refresh token
        mock_credentials = mock.Mock(spec=Credentials)
        mock_credentials.expired = True
        mock_credentials.refresh_token = None

        # Mock the Credentials constructor
        with mock.patch(
            "tournamentcontrol.competition.models.Credentials",
            return_value=mock_credentials,
        ):
            # Access the youtube property
            youtube_service = self.season.youtube

            # Verify refresh was NOT called (no refresh token available)
            mock_credentials.refresh.assert_not_called()

            # Verify build was still called (credentials passed as-is)
            mock_build.assert_called_once_with(
                "youtube", "v3", credentials=mock_credentials
            )
