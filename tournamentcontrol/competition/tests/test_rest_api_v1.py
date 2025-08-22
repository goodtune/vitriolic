import json

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
                        "ladder_summary": [],
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
        # Create matches with scores to trigger ladder summary generation via signals
        # Match 1: team1 wins 100-80
        factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.team1,
            away_team=self.team2,
            home_team_score=100,
            away_team_score=80,
        )

        # Match 2: team1 wins 50-40 (team2 home, team1 away)
        factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.team2,
            away_team=self.team1,
            home_team_score=40,
            away_team_score=50,
        )

        # Match 3: team2 wins 60-30 (team2 home, team1 away)
        factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.team2,
            away_team=self.team1,
            home_team_score=60,
            away_team_score=30,
        )

        self.get(
            "v1:division-detail",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            slug=self.division.slug,
        )
        self.response_200()

        # Parse the actual response to extract the key parts we want to validate
        actual_response = json.loads(self.last_response.content)

        # Find the ladder summary data by team ID for validation
        stage_data = actual_response["stages"][0]
        ladder_summary = stage_data["ladder_summary"]

        # Sort by team ID for consistent comparison
        ladder_summary.sort(key=lambda x: x["team"])

        # Expected ladder summary structure - team1 should have more points (2 wins vs 1 win)
        expected_ladder_summary = [
            {
                "team": self.team1.id,
                "played": 3,
                "win": 2,
                "loss": 1,
                "draw": 0,
                "bye": 0,
                "forfeit_for": 0,
                "forfeit_against": 0,
                "score_for": 180,
                "score_against": 180,
                "difference": "0.000",
                "percentage": "100.00",
                "points": "7.000",  # 3*2 + 1*1 = 7 (2 wins, 1 loss using division formula)
                "bonus_points": 0,
            },
            {
                "team": self.team2.id,
                "played": 3,
                "win": 1,
                "loss": 2,
                "draw": 0,
                "bye": 0,
                "forfeit_for": 0,
                "forfeit_against": 0,
                "score_for": 180,
                "score_against": 180,
                "difference": "0.000",
                "percentage": "100.00",
                "points": "5.000",  # 3*1 + 1*2 = 5 (1 win, 2 losses using division formula)
                "bonus_points": 0,
            },
        ]

        # Define expected complete response structure
        expected_response = {
            "title": self.division.title,
            "slug": self.division.slug,
            "url": f"http://testserver/api/v1/competitions/{self.competition.slug}/seasons/{self.season.slug}/divisions/{self.division.slug}/",
            "teams": [
                {
                    "id": self.team1.id,
                    "title": self.team1.title,
                    "slug": self.team1.slug,
                    "club": {
                        "title": self.team1.club.title,
                        "slug": self.team1.club.slug,
                        "abbreviation": "",
                        "short_title": "",
                        "url": f"http://testserver/api/v1/clubs/{self.team1.club.slug}/",
                        "website": "",
                        "facebook": "",
                        "twitter": "",
                        "youtube": "",
                    },
                },
                {
                    "id": self.team2.id,
                    "title": self.team2.title,
                    "slug": self.team2.slug,
                    "club": {
                        "title": self.team2.club.title,
                        "slug": self.team2.club.slug,
                        "abbreviation": "",
                        "short_title": "",
                        "url": f"http://testserver/api/v1/clubs/{self.team2.club.slug}/",
                        "website": "",
                        "facebook": "",
                        "twitter": "",
                        "youtube": "",
                    },
                },
            ],
            "stages": [
                {
                    "title": self.stage.title,
                    "slug": self.stage.slug,
                    "url": f"http://testserver/api/v1/competitions/{self.competition.slug}/seasons/{self.season.slug}/divisions/{self.division.slug}/stages/{self.stage.slug}/",
                    "matches": [
                        # We'll check that matches are included but not their exact structure since it includes varying data
                    ],
                    "ladder_summary": expected_ladder_summary,
                }
            ],
        }

        # Test the complete structure but extract matches separately since they have dynamic data
        actual_matches = stage_data["matches"]
        expected_response["stages"][0]["matches"] = actual_matches

        self.assertJSONEqual(self.last_response.content, expected_response)
