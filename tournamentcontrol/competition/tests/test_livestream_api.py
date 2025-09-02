"""
Test live streaming REST API endpoints.
"""

import json
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.urls import reverse
from test_plus import TestCase

from tournamentcontrol.competition.tests import factories

User = get_user_model()


class LiveStreamAPITests(TestCase):
    """Test LiveStreamViewSet REST API."""

    def setUp(self):
        """Create test fixtures."""
        # Create superuser for authentication
        self.user = self.make_user(is_superuser=True)
        
        # Create season with streaming capability
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
            ],
        )
        
        self.stage = factories.StageFactory.create(division__season=self.season)
        
        # Create matches with and without streaming
        self.stream_match_1 = factories.MatchFactory.create(
            stage=self.stage,
            external_identifier="youtube_id_1",
            live_stream=True,
            date=date(2023, 6, 15),
        )
        
        self.stream_match_2 = factories.MatchFactory.create(
            stage=self.stage,
            external_identifier="youtube_id_2",
            live_stream=True,
            date=date(2023, 6, 16),
        )
        
        # Match without streaming (should not appear in API)
        self.non_stream_match = factories.MatchFactory.create(
            stage=self.stage,
            external_identifier=None,
            live_stream=False,
            date=date(2023, 6, 15),
        )
        
        # Match with empty external_identifier (should not appear)
        self.empty_id_match = factories.MatchFactory.create(
            stage=self.stage,
            external_identifier="",
            live_stream=True,
            date=date(2023, 6, 15),
        )

    def test_unauthenticated_access_denied(self):
        """Test that unauthenticated requests are denied."""
        url = reverse('v1:livestream-list', kwargs={
            'competition_slug': self.season.competition.slug,
            'season_slug': self.season.slug,
        })
        
        response = self.get(url)
        self.response_401(response)

    def test_list_matches_grouped_by_date(self):
        """Test listing matches grouped by date."""
        self.login(self.user)
        
        url = reverse('v1:livestream-list', kwargs={
            'competition_slug': self.season.competition.slug,
            'season_slug': self.season.slug,
        })
        
        response = self.get(url)
        self.response_200(response)
        
        data = response.json()
        
        # Should have two dates
        self.assertEqual(len(data), 2)
        self.assertIn('2023-06-15', data)
        self.assertIn('2023-06-16', data)
        
        # 2023-06-15 should have only one match (stream_match_1)
        # non_stream_match and empty_id_match should be filtered out
        self.assertEqual(len(data['2023-06-15']), 1)
        self.assertEqual(data['2023-06-15'][0]['external_identifier'], 'youtube_id_1')
        
        # 2023-06-16 should have one match
        self.assertEqual(len(data['2023-06-16']), 1)
        self.assertEqual(data['2023-06-16'][0]['external_identifier'], 'youtube_id_2')

    def test_date_range_filtering(self):
        """Test filtering matches by date range."""
        self.login(self.user)
        
        url = reverse('v1:livestream-list', kwargs={
            'competition_slug': self.season.competition.slug,
            'season_slug': self.season.slug,
        })
        
        # Filter for only 2023-06-15
        response = self.get(url + '?date_gte=2023-06-15&date_lte=2023-06-15')
        self.response_200(response)
        
        data = response.json()
        
        # Should only have 2023-06-15
        self.assertEqual(len(data), 1)
        self.assertIn('2023-06-15', data)
        self.assertNotIn('2023-06-16', data)

    def test_season_filtering(self):
        """Test filtering matches by season ID."""
        # Create another season with matches
        other_season = factories.SeasonFactory.create()
        other_stage = factories.StageFactory.create(division__season=other_season)
        other_match = factories.MatchFactory.create(
            stage=other_stage,
            external_identifier="other_youtube_id",
            live_stream=True,
        )
        
        self.login(self.user)
        
        url = reverse('v1:livestream-list', kwargs={
            'competition_slug': self.season.competition.slug,
            'season_slug': self.season.slug,
        })
        
        # Filter by original season ID
        response = self.get(url + f'?season_id={self.season.id}')
        self.response_200(response)
        
        data = response.json()
        
        # Should only contain matches from original season
        all_external_ids = []
        for date_matches in data.values():
            for match in date_matches:
                all_external_ids.append(match['external_identifier'])
        
        self.assertIn('youtube_id_1', all_external_ids)
        self.assertIn('youtube_id_2', all_external_ids)
        self.assertNotIn('other_youtube_id', all_external_ids)

    def test_match_serialization_includes_nested_details(self):
        """Test that match serialization includes nested Stage/Division/Season/Competition."""
        self.login(self.user)
        
        url = reverse('v1:livestream-list', kwargs={
            'competition_slug': self.season.competition.slug,
            'season_slug': self.season.slug,
        })
        
        response = self.get(url)
        self.response_200(response)
        
        data = response.json()
        match_data = data['2023-06-15'][0]
        
        # Check nested structure
        self.assertIn('stage', match_data)
        stage_data = match_data['stage']
        
        self.assertIn('division', stage_data)
        division_data = stage_data['division']
        
        self.assertIn('season', division_data)
        season_data = division_data['season']
        
        self.assertIn('competition', season_data)
        competition_data = season_data['competition']
        
        # Verify actual values
        self.assertEqual(stage_data['id'], self.stage.id)
        self.assertEqual(division_data['id'], self.stage.division.id)
        self.assertEqual(season_data['id'], self.season.id)
        self.assertEqual(competition_data['id'], self.season.competition.id)

    def test_invalid_date_formats_ignored(self):
        """Test that invalid date formats in query params are ignored."""
        self.login(self.user)
        
        url = reverse('v1:livestream-list', kwargs={
            'competition_slug': self.season.competition.slug,
            'season_slug': self.season.slug,
        })
        
        # Use invalid date formats
        response = self.get(url + '?date_gte=invalid-date&date_lte=not-a-date')
        self.response_200(response)
        
        # Should return all matches (invalid filters ignored)
        data = response.json()
        self.assertEqual(len(data), 2)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_transition_endpoint_success(self, mock_build):
        """Test successful live stream transition via API."""
        # Mock YouTube service
        mock_youtube = mock.Mock()
        mock_response = {'id': 'youtube_id_1', 'status': {'lifeCycleStatus': 'live'}}
        mock_youtube.liveBroadcasts.return_value.transition.return_value.execute.return_value = mock_response
        mock_build.return_value = mock_youtube
        
        self.login(self.user)
        
        url = reverse('v1:livestream-transition', kwargs={
            'competition_slug': self.season.competition.slug,
            'season_slug': self.season.slug,
            'uuid': self.stream_match_1.uuid,
        })
        
        data = {'status': 'live'}
        response = self.client.post(
            url, 
            data=json.dumps(data), 
            content_type='application/json'
        )
        
        self.response_200(response)
        
        result = response.json()
        self.assertTrue(result['success'])
        self.assertEqual(result['message'], 'Successfully transitioned to live')
        self.assertEqual(result['youtube_response'], mock_response)
        self.assertEqual(result['warnings'], [])

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_transition_endpoint_with_warnings(self, mock_build):
        """Test transition endpoint includes warnings in response."""
        # Mock YouTube service to return current status that would trigger warning
        mock_youtube = mock.Mock()
        mock_list_response = {
            'items': [{'status': {'lifeCycleStatus': 'live'}}]
        }
        mock_youtube.liveBroadcasts.return_value.list.return_value.execute.return_value = mock_list_response
        
        mock_transition_response = {'status': 'testing'}
        mock_youtube.liveBroadcasts.return_value.transition.return_value.execute.return_value = mock_transition_response
        mock_build.return_value = mock_youtube
        
        self.login(self.user)
        
        url = reverse('v1:livestream-transition', kwargs={
            'competition_slug': self.season.competition.slug,
            'season_slug': self.season.slug,
            'uuid': self.stream_match_1.uuid,
        })
        
        data = {'status': 'testing'}
        response = self.client.post(
            url, 
            data=json.dumps(data), 
            content_type='application/json'
        )
        
        self.response_200(response)
        
        result = response.json()
        self.assertTrue(result['success'])
        self.assertEqual(len(result['warnings']), 1)
        self.assertIn("Potentially invalid transition", result['warnings'][0])

    def test_transition_endpoint_invalid_status(self):
        """Test transition endpoint with invalid status value."""
        self.login(self.user)
        
        url = reverse('v1:livestream-transition', kwargs={
            'competition_slug': self.season.competition.slug,
            'season_slug': self.season.slug,
            'uuid': self.stream_match_1.uuid,
        })
        
        data = {'status': 'invalid_status'}
        response = self.client.post(
            url, 
            data=json.dumps(data), 
            content_type='application/json'
        )
        
        self.response_400(response)
        
        result = response.json()
        self.assertIn('status', result)

    def test_transition_endpoint_missing_external_identifier(self):
        """Test transition endpoint with match lacking external_identifier."""
        self.login(self.user)
        
        url = reverse('v1:livestream-transition', kwargs={
            'competition_slug': self.season.competition.slug,
            'season_slug': self.season.slug,
            'uuid': self.non_stream_match.uuid,
        })
        
        data = {'status': 'live'}
        response = self.client.post(
            url, 
            data=json.dumps(data), 
            content_type='application/json'
        )
        
        self.response_400(response)
        
        result = response.json()
        self.assertFalse(result['success'])
        self.assertIn('does not have a live stream identifier', result['error'])

    def test_permission_check_non_superuser(self):
        """Test that regular users without permissions are denied access."""
        # Create regular user
        regular_user = self.make_user()
        self.login(regular_user)
        
        url = reverse('v1:livestream-list', kwargs={
            'competition_slug': self.season.competition.slug,
            'season_slug': self.season.slug,
        })
        
        response = self.get(url)
        self.response_403(response)

    def test_retrieve_specific_match(self):
        """Test retrieving a specific match by UUID."""
        self.login(self.user)
        
        url = reverse('v1:livestream-detail', kwargs={
            'competition_slug': self.season.competition.slug,
            'season_slug': self.season.slug,
            'uuid': self.stream_match_1.uuid,
        })
        
        response = self.get(url)
        self.response_200(response)
        
        data = response.json()
        self.assertEqual(data['uuid'], str(self.stream_match_1.uuid))
        self.assertEqual(data['external_identifier'], 'youtube_id_1')