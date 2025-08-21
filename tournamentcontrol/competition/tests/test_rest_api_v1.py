from django.test.utils import override_settings
from test_plus import TestCase

from tournamentcontrol.competition.tests import factories


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class APITests(TestCase):

    @classmethod
    def setUpTestData(cls):
        """Create test data once for all tests."""
        # Create a club
        cls.club = factories.ClubFactory.create()

        # Create a competition with a known slug
        cls.competition = factories.CompetitionFactory.create()

        # Create a season with a known slug
        cls.season = factories.SeasonFactory.create(competition=cls.competition)

        # Create a division with a known slug
        cls.division = factories.DivisionFactory.create(season=cls.season)

        # Create a stage
        cls.stage = factories.StageFactory.create(division=cls.division)

        # Create teams
        cls.team1 = factories.TeamFactory.create(club=cls.club, division=cls.division)
        cls.team2 = factories.TeamFactory.create(division=cls.division)

        # Create a person for players endpoints
        cls.person = factories.PersonFactory.create(club=cls.club)
        cls.team_association = factories.TeamAssociationFactory.create(
            team=cls.team1, person=cls.person
        )

        # Create a venue and ground for matches
        cls.venue = factories.VenueFactory.create(season=cls.season)
        cls.ground = factories.GroundFactory.create(venue=cls.venue)

        # Create a match
        cls.match = factories.MatchFactory.create(
            stage=cls.stage,
            home_team=cls.team1,
            away_team=cls.team2,
            play_at=cls.ground,
        )

    def test_club_list(self):
        """Test club-list endpoint"""
        self.get("v1:club-list")
        self.response_200()

    def test_club_detail(self):
        """Test club-detail endpoint"""
        self.get("v1:club-detail", slug=self.club.slug)
        self.response_200()

    def test_competition_list(self):
        """Test competition-list endpoint"""
        self.get("v1:competition-list")
        self.response_200()

    def test_competition_detail(self):
        """Test competition-detail endpoint"""
        self.get("v1:competition-detail", slug=self.competition.slug)
        self.response_200()

    def test_season_list(self):
        """Test season-list endpoint"""
        self.get(
            "v1:season-list",
            competition_slug=self.competition.slug,
        )
        self.response_200()

    def test_season_detail(self):
        """Test season-detail endpoint"""
        self.get(
            "v1:season-detail",
            competition_slug=self.competition.slug,
            slug=self.season.slug,
        )
        self.response_200()

    def test_division_list(self):
        """Test division-list endpoint"""
        self.get(
            "v1:division-list",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
        )
        self.response_200()

    def test_division_detail(self):
        """Test division-detail endpoint"""
        self.get(
            "v1:division-detail",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            slug=self.division.slug,
        )
        self.response_200()

        # Validate that the response contains the expected data, including timezone serialization.
        self.assertJSONEqual(
            self.last_response.content,
            {
                "title": self.division.title,
                "slug": self.division.slug,
                "url": f"http://testserver/api/v1/competitions/{self.competition.slug}/seasons/{self.season.slug}/divisions/{self.division.slug}/",
                "teams": [
                    {
                        "id": self.team1.id,
                        "title": self.team1.title,
                        "slug": self.team1.slug,
                        "club": {
                            "abbreviation": self.club.abbreviation,
                            "facebook": self.club.facebook,
                            "short_title": self.club.short_title,
                            "slug": self.club.slug,
                            "title": self.club.title,
                            "twitter": self.club.twitter,
                            "url": f"http://testserver/api/v1/clubs/{self.club.slug}/",
                            "website": self.club.website,
                            "youtube": self.club.youtube,
                        },
                    },
                    {
                        "id": self.team2.id,
                        "title": self.team2.title,
                        "slug": self.team2.slug,
                        "club": {
                            "abbreviation": self.team2.club.abbreviation,
                            "facebook": self.team2.club.facebook,
                            "short_title": self.team2.club.short_title,
                            "slug": self.team2.club.slug,
                            "title": self.team2.club.title,
                            "twitter": self.team2.club.twitter,
                            "url": f"http://testserver/api/v1/clubs/{self.team2.club.slug}/",
                            "website": self.team2.club.website,
                            "youtube": self.team2.club.youtube,
                        },
                    },
                ],
                "stages": [
                    {
                        "title": self.stage.title,
                        "slug": self.stage.slug,
                        "url": f"http://testserver/api/v1/competitions/{self.competition.slug}/seasons/{self.season.slug}/divisions/{self.division.slug}/stages/{self.stage.slug}/",
                        "matches": [
                            {
                                "id": self.match.id,
                                "uuid": str(self.match.uuid),
                                "round": f"Round {self.match.round}",
                                "date": self.match.date.isoformat(),
                                "time": self.match.time.isoformat(),
                                "datetime": self.match.datetime.strftime(
                                    "%Y-%m-%dT%H:%M:%S.%fZ"
                                ),
                                "is_bye": False,
                                "is_washout": False,
                                "home_team": self.team1.id,
                                "home_team_score": None,
                                "away_team": self.team2.id,
                                "away_team_score": None,
                                "referees": [],
                                "videos": None,
                                "play_at": {
                                    "id": self.ground.id,
                                    "title": self.ground.title,
                                    "abbreviation": None,
                                    "timezone": str(self.ground.timezone),
                                },
                            },
                        ],
                    }
                ],
            },
        )

    def test_players_list(self):
        """Test players-list endpoint"""
        self.get(
            "v1:players-list",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
        )
        self.response_200()

    def test_players_detail(self):
        """Test players-detail endpoint"""
        self.get(
            "v1:players-detail",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            id=self.team_association.pk,
        )
        self.response_200()

    def test_match_list(self):
        """Test match-list endpoint"""
        self.get(
            "v1:match-list",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
        )
        self.response_200()

    def test_match_detail(self):
        """Test match-detail endpoint"""
        self.get(
            "v1:match-detail",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            uuid=self.match.uuid,
        )
        self.response_200()

    def test_stage_list(self):
        """Test stage-list endpoint"""
        self.get(
            "v1:stage-list",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            division_slug=self.division.slug,
        )
        self.response_200()

    def test_stage_detail(self):
        """Test stage-detail endpoint"""
        self.get(
            "v1:stage-detail",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            division_slug=self.division.slug,
            slug=self.stage.slug,
        )
        self.response_200()

    def test_division_detail_includes_ladder_summary(self):
        """Test that division-detail endpoint includes ladder_summary in stages"""
        # Create some ladder summary data
        from tournamentcontrol.competition.models import LadderSummary
        
        ladder1 = LadderSummary.objects.create(
            stage=self.stage,
            team=self.team1,
            played=5,
            win=3,
            loss=2,
            score_for=100,
            score_against=80,
            difference=20,
            points=6,
        )
        ladder2 = LadderSummary.objects.create(
            stage=self.stage,
            team=self.team2,
            played=5,
            win=2,
            loss=3,
            score_for=80,
            score_against=100,
            difference=-20,
            points=4,
        )

        self.get(
            "v1:division-detail",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            slug=self.division.slug,
        )
        self.response_200()
        
        # Parse the response
        import json
        response_data = json.loads(self.last_response.content)
        
        # Ensure stages have ladder_summary field
        self.assertIn("stages", response_data)
        self.assertEqual(len(response_data["stages"]), 1)
        
        stage_data = response_data["stages"][0]
        self.assertIn("ladder_summary", stage_data)
        
        # Check ladder summary data
        ladder_summary = stage_data["ladder_summary"]
        self.assertEqual(len(ladder_summary), 2)
        
        # Sort by points to ensure consistent order
        ladder_summary.sort(key=lambda x: x["points"], reverse=True)
        
        # Check first team (higher points)
        first_team = ladder_summary[0]
        self.assertEqual(first_team["team"]["id"], self.team1.id)
        self.assertEqual(first_team["played"], 5)
        self.assertEqual(first_team["win"], 3)
        self.assertEqual(first_team["loss"], 2)
        self.assertEqual(first_team["score_for"], 100)
        self.assertEqual(first_team["score_against"], 80)
        self.assertEqual(first_team["difference"], "20.000")
        self.assertEqual(first_team["points"], "6.000")
        
        # Check second team (lower points)
        second_team = ladder_summary[1]
        self.assertEqual(second_team["team"]["id"], self.team2.id)
        self.assertEqual(second_team["played"], 5)
        self.assertEqual(second_team["win"], 2)
        self.assertEqual(second_team["loss"], 3)
        self.assertEqual(second_team["score_for"], 80)
        self.assertEqual(second_team["score_against"], 100)
        self.assertEqual(second_team["difference"], "-20.000")
        self.assertEqual(second_team["points"], "4.000")
