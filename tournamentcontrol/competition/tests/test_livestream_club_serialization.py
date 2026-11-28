"""
Test to verify that team serialization with clubs works correctly.
"""

from django.test.utils import override_settings
from test_plus import TestCase

from tournamentcontrol.competition.tests.factories import SuperUserFactory


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class TeamClubSerializationTest(TestCase):
    """Test team serialization in livestream context includes club data properly."""
    
    user_factory = SuperUserFactory

    def setUp(self):
        """Create test fixtures."""
        from tournamentcontrol.competition.tests import factories
        
        # Create superuser for authentication
        self.user = self.make_user()
        
        # Create season with streaming capability
        self.season = factories.SeasonFactory.create(live_stream=True)
        self.stage = factories.StageFactory.create(division__season=self.season)
        
        # Create match with teams that have clubs
        self.match = factories.MatchFactory.create(
            stage=self.stage,
            external_identifier="youtube_id_test",
            live_stream=True,
        )

    def test_team_serialization_includes_club_data(self):
        """Test that team serialization includes club data without URL errors."""
        self.login(self.user)
        
        self.get('v1:competition:livestream-list')
        self.response_200()
        
        data = self.last_response.json()
        
        # Get the first match from any date
        first_date = list(data.keys())[0]
        match_data = data[first_date][0]
        
        # Verify team structure includes club data
        self.assertIn('home_team', match_data)
        self.assertIn('away_team', match_data)
        
        home_team = match_data['home_team']
        away_team = match_data['away_team']
        
        # Verify club data is present and properly structured
        if home_team['club'] is not None:  # Skip if it's a ByeTeam
            self.assertIn('id', home_team['club'])
            self.assertIn('title', home_team['club'])
            self.assertIn('slug', home_team['club'])
            self.assertIn('abbreviation', home_team['club'])
            self.assertIn('status', home_team['club'])
            
        if away_team['club'] is not None:  # Skip if it's a ByeTeam
            self.assertIn('id', away_team['club'])
            self.assertIn('title', away_team['club'])
            self.assertIn('slug', away_team['club'])
            self.assertIn('abbreviation', away_team['club'])
            self.assertIn('status', away_team['club'])

    def test_retrieve_specific_match_with_club_data(self):
        """Test retrieving a specific match includes proper club serialization."""
        self.login(self.user)
        
        self.get('v1:competition:livestream-detail', uuid=self.match.uuid)
        self.response_200()
        
        data = self.last_response.json()
        
        # Verify club data structure is correct
        home_team = data['home_team']
        away_team = data['away_team']
        
        # Test that we can access club data without errors
        if home_team['club']:
            self.assertEqual(home_team['club']['id'], self.match.home_team.club.id)
            self.assertEqual(home_team['club']['title'], self.match.home_team.club.title)
            
        if away_team['club']:
            self.assertEqual(away_team['club']['id'], self.match.away_team.club.id)
            self.assertEqual(away_team['club']['title'], self.match.away_team.club.title)