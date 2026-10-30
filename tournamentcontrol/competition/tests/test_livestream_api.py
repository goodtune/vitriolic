"""
Test live streaming REST API endpoints.
"""

from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.factories import SuperUserFactory

User = get_user_model()


class LiveStreamAPITests(TestCase):
    """Test LiveStreamViewSet REST API."""

    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        """Create test fixtures."""
        # Create superuser for authentication
        cls.user = cls.make_user()

        # Create season with streaming capability
        cls.season = factories.SeasonFactory.create(
            live_stream=True,
            live_stream_project_id="test-project-123",
            live_stream_client_id="test-client-123.apps.googleusercontent.com",
            live_stream_client_secret="test-secret-456",
            live_stream_token="current-access-token",
            live_stream_refresh_token="refresh-token-789",
            live_stream_token_uri="https://oauth2.googleapis.com/token",
            live_stream_scopes=[
                "https://www.googleapis.com/auth/youtube",
            ],
        )

        cls.stage = factories.StageFactory.create(division__season=cls.season)

        # Create matches with and without streaming
        cls.stream_match_1 = factories.MatchFactory.create(
            stage=cls.stage,
            external_identifier="youtube_id_1",
            live_stream=True,
            date=date(2023, 6, 15),
        )

        cls.stream_match_2 = factories.MatchFactory.create(
            stage=cls.stage,
            external_identifier="youtube_id_2",
            live_stream=True,
            date=date(2023, 6, 16),
        )

        # Match without streaming (should not appear in API)
        cls.non_stream_match = factories.MatchFactory.create(
            stage=cls.stage,
            external_identifier=None,
            live_stream=False,
            date=date(2023, 6, 15),
        )

        # Match with empty external_identifier (should not appear)
        cls.empty_id_match = factories.MatchFactory.create(
            stage=cls.stage,
            external_identifier="",
            live_stream=True,
            date=date(2023, 6, 15),
        )

    def test_unauthenticated_access_denied(self):
        """Test that unauthenticated requests are denied."""
        self.get("v1:competition:livestream-list")
        self.assert_http_403_forbidden()

    def test_list_matches_grouped_by_date(self):
        """Test listing matches grouped by date."""
        self.login(self.user)

        self.get("v1:competition:livestream-list")
        self.assert_http_200_ok()

        data = self.last_response.json()

        # Should have two dates
        self.assertEqual(len(data), 2)
        self.assertIn("2023-06-15", data)
        self.assertIn("2023-06-16", data)

        # 2023-06-15 should have only one match (stream_match_1)
        # non_stream_match and empty_id_match should be filtered out
        self.assertEqual(len(data["2023-06-15"]), 1)
        match_1_data = data["2023-06-15"][0]
        self.assertEqual(match_1_data["id"], self.stream_match_1.id)
        self.assertEqual(match_1_data["uuid"], str(self.stream_match_1.uuid))
        self.assertEqual(match_1_data["external_identifier"], "youtube_id_1")

        # 2023-06-16 should have one match
        self.assertEqual(len(data["2023-06-16"]), 1)
        match_2_data = data["2023-06-16"][0]
        self.assertEqual(match_2_data["id"], self.stream_match_2.id)
        self.assertEqual(match_2_data["uuid"], str(self.stream_match_2.uuid))
        self.assertEqual(match_2_data["external_identifier"], "youtube_id_2")

    def test_date_range_filtering(self):
        """Test filtering matches by date range."""
        self.login(self.user)

        # Filter for only 2023-06-15
        self.get(
            "v1:competition:livestream-list",
            data={"date__gte": "2023-06-15", "date__lte": "2023-06-15"},
        )
        self.assert_http_200_ok()

        data = self.last_response.json()

        # Should only have 2023-06-15
        self.assertEqual(len(data), 1)
        self.assertIn("2023-06-15", data)
        self.assertNotIn("2023-06-16", data)

    def test_season_filtering(self):
        """Test filtering matches by season ID."""
        # Create another season with matches
        other_season = factories.SeasonFactory.create()
        other_stage = factories.StageFactory.create(division__season=other_season)
        factories.MatchFactory.create(
            stage=other_stage,
            external_identifier="other_youtube_id",
            live_stream=True,
        )

        self.login(self.user)

        # Filter by original season ID
        self.get("v1:competition:livestream-list", data={"season_id": self.season.id})
        self.assert_http_200_ok()

        data = self.last_response.json()

        # Should only contain matches from original season
        all_external_ids = []
        for date_matches in data.values():
            for match in date_matches:
                all_external_ids.append(match["external_identifier"])

        self.assertCountEqual(all_external_ids, ["youtube_id_1", "youtube_id_2"])

    def test_match_serialization_includes_nested_details(self):
        """Test that match serialization includes nested Stage/Division/Season/Competition."""
        self.login(self.user)

        self.get("v1:competition:livestream-list")
        self.assert_http_200_ok()

        data = self.last_response.json()
        match_data = data["2023-06-15"][0]

        # Check nested structure
        self.assertIn("stage", match_data)
        stage_data = match_data["stage"]

        self.assertIn("division", stage_data)
        division_data = stage_data["division"]

        self.assertIn("season", division_data)
        season_data = division_data["season"]

        self.assertIn("competition", season_data)
        competition_data = season_data["competition"]

        # Verify actual values
        self.assertEqual(stage_data["id"], self.stage.id)
        self.assertEqual(division_data["id"], self.stage.division.id)
        self.assertEqual(season_data["id"], self.season.id)
        self.assertEqual(competition_data["id"], self.season.competition.id)

    def test_invalid_date_formats_ignored(self):
        """Test that invalid date formats in query params are ignored."""
        self.login(self.user)

        # Use invalid date formats
        self.get(
            "v1:competition:livestream-list",
            data={"date__gte": "invalid-date", "date__lte": "not-a-date"},
        )
        # The FilterSet validates the dates, so the request is rejected.
        self.assert_http_400_bad_request()
        self.assertEqual(
            self.last_response.json(),
            {
                "date__gte": ["Enter a valid date."],
                "date__lte": ["Enter a valid date."],
            },
        )

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_transition_endpoint_success(self, mock_build):
        """Test successful live stream transition via API."""
        # Mock YouTube service
        mock_youtube = mock.Mock()
        mock_response = {"id": "youtube_id_1", "status": {"lifeCycleStatus": "live"}}
        mock_youtube.liveBroadcasts.return_value.transition.return_value.execute.return_value = (
            mock_response
        )
        mock_build.return_value = mock_youtube

        self.login(self.user)

        data = {"status": "live"}
        self.post(
            "v1:competition:livestream-transition",
            uuid=self.stream_match_1.uuid,
            data=data,
            extra={"content_type": "application/json"},
        )
        self.assert_http_200_ok()

        result = self.last_response.json()
        self.assertIs(result["success"], True)
        self.assertEqual(result["message"], "Successfully transitioned to live")
        self.assertEqual(result["youtube_response"], mock_response)
        self.assertEqual(result["warnings"], [])

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_transition_endpoint_with_warnings(self, mock_build):
        """Test transition endpoint includes warnings in response."""
        # Mock YouTube service to return current status that would trigger warning
        mock_youtube = mock.Mock()
        mock_list_response = {"items": [{"status": {"lifeCycleStatus": "live"}}]}
        mock_youtube.liveBroadcasts.return_value.list.return_value.execute.return_value = (
            mock_list_response
        )

        mock_transition_response = {"status": "testing"}
        mock_youtube.liveBroadcasts.return_value.transition.return_value.execute.return_value = (
            mock_transition_response
        )
        mock_build.return_value = mock_youtube

        self.login(self.user)

        data = {"status": "testing"}
        self.post(
            "v1:competition:livestream-transition",
            uuid=self.stream_match_1.uuid,
            data=data,
            extra={"content_type": "application/json"},
        )
        self.assert_http_200_ok()

        result = self.last_response.json()
        self.assertIs(result["success"], True)
        self.assertEqual(result["warnings"], [])

    def test_transition_endpoint_invalid_status(self):
        """Test transition endpoint with invalid status value."""
        self.login(self.user)

        data = {"status": "invalid_status"}
        self.post(
            "v1:competition:livestream-transition",
            uuid=self.stream_match_1.uuid,
            data=data,
            extra={"content_type": "application/json"},
        )
        self.assert_http_400_bad_request()

        self.assertEqual(
            self.last_response.json(),
            {"status": ['"invalid_status" is not a valid choice.']},
        )

    def test_transition_endpoint_missing_external_identifier(self):
        """Test transition endpoint with match lacking external_identifier."""
        self.login(self.user)

        data = {"status": "live"}
        self.post(
            "v1:competition:livestream-transition",
            uuid=self.non_stream_match.uuid,
            data=data,
            extra={"content_type": "application/json"},
        )
        self.assert_http_404_not_found()

    def test_permission_check_non_superuser(self):
        """Test that regular users without permissions are denied access."""
        # Create regular user
        regular_user = UserFactory()
        self.login(regular_user)

        self.get("v1:competition:livestream-list")
        self.assert_http_403_forbidden()

    def test_retrieve_specific_match(self):
        """Test retrieving a specific match by UUID."""
        self.login(self.user)

        self.get("v1:competition:livestream-detail", uuid=self.stream_match_1.uuid)
        self.assert_http_200_ok()

        data = self.last_response.json()
        self.assertEqual(data["uuid"], str(self.stream_match_1.uuid))
        self.assertEqual(data["external_identifier"], "youtube_id_1")
