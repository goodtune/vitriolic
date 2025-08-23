
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
        stage = factories.StageFactory.create(division__season=self.season)

        # Create matches with scores to trigger ladder summary generation via signals
        # Match 1: team1 wins 100-80
        match1 = factories.MatchFactory.create(
            stage=stage,
            play_at=self.ground,
            home_team_score=100,
            away_team_score=80,
            date="2025-08-22",
            time="09:00:00",
            datetime="2025-08-22T09:00:00.000000Z",
            round=1,
        )

        # Match 2: team1 wins 50-40 (team2 home, team1 away)
        match2 = factories.MatchFactory.create(
            stage=stage,
            play_at=self.ground,
            home_team=match1.away_team,
            away_team=match1.home_team,
            home_team_score=40,
            away_team_score=50,
            date="2025-08-22",
            time="12:00:00",
            datetime="2025-08-22T12:00:00.000000Z",
            round=2,
        )

        # Match 3: team2 wins 60-30 (team2 home, team1 away)
        match3 = factories.MatchFactory.create(
            stage=stage,
            play_at=self.ground,
            home_team=match1.away_team,
            away_team=match1.home_team,
            home_team_score=60,
            away_team_score=30,
            date="2025-08-22",
            time="15:00:00",
            datetime="2025-08-22T15:00:00.000000Z",
            round=3,
        )

        self.get(
            "v1:division-detail",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            slug=stage.division.slug,
        )
        self.response_200()

        expected_payload = {
            "title": stage.division.title,
            "slug": stage.division.slug,
            "url": f"http://testserver/api/v1/competitions/{self.competition.slug}/seasons/{self.season.slug}/divisions/{stage.division.slug}/",
            "teams": [
                {
                    "id": match1.home_team.id,
                    "title": match1.home_team.title,
                    "slug": match1.home_team.slug,
                    "club": {
                        "abbreviation": match1.home_team.club.abbreviation,
                        "facebook": match1.home_team.club.facebook,
                        "short_title": match1.home_team.club.short_title,
                        "slug": match1.home_team.club.slug,
                        "title": match1.home_team.club.title,
                        "twitter": match1.home_team.club.twitter,
                        "url": f"http://testserver/api/v1/clubs/{match1.home_team.club.slug}/",
                        "website": match1.home_team.club.website,
                        "youtube": match1.home_team.club.youtube,
                    },
                },
                {
                    "id": match1.away_team.id,
                    "title": match1.away_team.title,
                    "slug": match1.away_team.slug,
                    "club": {
                        "abbreviation": match1.away_team.club.abbreviation,
                        "facebook": match1.away_team.club.facebook,
                        "short_title": match1.away_team.club.short_title,
                        "slug": match1.away_team.club.slug,
                        "title": match1.away_team.club.title,
                        "twitter": match1.away_team.club.twitter,
                        "url": f"http://testserver/api/v1/clubs/{match1.away_team.club.slug}/",
                        "website": match1.away_team.club.website,
                        "youtube": match1.away_team.club.youtube,
                    },
                },
            ],
            "stages": [
                {
                    "title": stage.title,
                    "slug": stage.slug,
                    "url": f"http://testserver/api/v1/competitions/{self.competition.slug}/seasons/{self.season.slug}/divisions/{stage.division.slug}/stages/{stage.slug}/",
                    "matches": [
                        {
                            "id": match1.id,
                            "uuid": str(match1.uuid),
                            "round": "Round 1",
                            "date": "2025-08-22",
                            "time": "09:00:00",
                            "datetime": "2025-08-22T09:00:00Z",
                            "is_bye": False,
                            "is_washout": False,
                            "home_team": match1.home_team.id,
                            "home_team_score": 100,
                            "away_team": match1.away_team.id,
                            "away_team_score": 80,
                            "referees": [],
                            "videos": None,
                            "play_at": {
                                "id": self.ground.id,
                                "title": self.ground.title,
                                "abbreviation": self.ground.abbreviation,
                                "timezone": str(self.ground.timezone),
                            },
                        },
                        {
                            "id": match2.id,
                            "uuid": str(match2.uuid),
                            "round": "Round 2",
                            "date": "2025-08-22",
                            "time": "12:00:00",
                            "datetime": "2025-08-22T12:00:00Z",
                            "is_bye": False,
                            "is_washout": False,
                            "home_team": match2.home_team.id,
                            "home_team_score": 40,
                            "away_team": match2.away_team.id,
                            "away_team_score": 50,
                            "referees": [],
                            "videos": None,
                            "play_at": {
                                "id": self.ground.id,
                                "title": self.ground.title,
                                "abbreviation": self.ground.abbreviation,
                                "timezone": str(self.ground.timezone),
                            },
                        },
                        {
                            "id": match3.id,
                            "uuid": str(match3.uuid),
                            "round": "Round 3",
                            "date": "2025-08-22",
                            "time": "15:00:00",
                            "datetime": "2025-08-22T15:00:00Z",
                            "is_bye": False,
                            "is_washout": False,
                            "home_team": match3.home_team.id,
                            "home_team_score": 60,
                            "away_team": match3.away_team.id,
                            "away_team_score": 30,
                            "referees": [],
                            "videos": None,
                            "play_at": {
                                "id": self.ground.id,
                                "title": self.ground.title,
                                "abbreviation": self.ground.abbreviation,
                                "timezone": str(self.ground.timezone),
                            },
                        },
                    ],
                    "ladder_summary": [
                        {
                            "team": match1.home_team.id,
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
                            "points": "7.000",
                            "bonus_points": 0,
                        },
                        {
                            "team": match1.away_team.id,
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
                            "points": "5.000",
                            "bonus_points": 0,
                        },
                    ],
                }
            ],
        }
        self.assertJSONEqual(self.last_response.content, expected_payload)

    def test_stage_groups_exposure_in_api(self):
        """Test that stage groups (pools) are properly exposed in the API"""
        # Create a stage with pools
        stage_with_pools = factories.StageFactory.create(division__season=self.season)

        # Create stage groups (pools)
        pool1 = factories.StageGroupFactory.create(
            stage=stage_with_pools, title="Pool A"
        )
        pool2 = factories.StageGroupFactory.create(
            stage=stage_with_pools, title="Pool B"
        )

        # Create teams for the pools
        team_pool1_1 = factories.TeamFactory.create(division=stage_with_pools.division)
        team_pool1_2 = factories.TeamFactory.create(division=stage_with_pools.division)
        team_pool2_1 = factories.TeamFactory.create(division=stage_with_pools.division)
        team_pool2_2 = factories.TeamFactory.create(division=stage_with_pools.division)

        # Create matches in pools
        match_pool1 = factories.MatchFactory.create(
            stage=stage_with_pools,
            stage_group=pool1,
            home_team=team_pool1_1,
            away_team=team_pool1_2,
            play_at=self.ground,
        )
        match_pool2 = factories.MatchFactory.create(
            stage=stage_with_pools,
            stage_group=pool2,
            home_team=team_pool2_1,
            away_team=team_pool2_2,
            play_at=self.ground,
        )

        # Create ladder summary entries for pools
        factories.LadderSummaryFactory.create(
            stage=stage_with_pools,
            stage_group=pool1,
            team=team_pool1_1,
        )
        factories.LadderSummaryFactory.create(
            stage=stage_with_pools,
            stage_group=pool1,
            team=team_pool1_2,
        )

        # Test division detail endpoint
        self.get(
            "v1:division-detail",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            slug=stage_with_pools.division.slug,
        )
        self.response_200()

        response_data = self.last_response.json()

        # Find our stage in the response
        stage_data = None
        for stage in response_data["stages"]:
            if stage["slug"] == stage_with_pools.slug:
                stage_data = stage
                break

        self.assertIsNotNone(stage_data, "Stage with pools not found in response")

        # Validate pools are exposed
        self.assertIn("pools", stage_data, "pools field missing from stage data")
        pools = stage_data["pools"]
        self.assertEqual(len(pools), 2, f"Expected 2 pools, got {len(pools)}")

        # Validate pool structure
        pool_ids = [pool["id"] for pool in pools]
        pool_titles = [pool["title"] for pool in pools]
        self.assertIn(pool1.pk, pool_ids, "Pool 1 ID not found in pools")
        self.assertIn(pool2.pk, pool_ids, "Pool 2 ID not found in pools")
        self.assertIn("Pool A", pool_titles, "Pool A title not found")
        self.assertIn("Pool B", pool_titles, "Pool B title not found")

        # Validate matches have stage_group field
        matches = stage_data["matches"]
        match_pool1_data = None
        match_pool2_data = None

        for match in matches:
            if match["id"] == match_pool1.id:
                match_pool1_data = match
            elif match["id"] == match_pool2.id:
                match_pool2_data = match

        self.assertIsNotNone(match_pool1_data, "Match from pool 1 not found")
        self.assertIsNotNone(match_pool2_data, "Match from pool 2 not found")

        self.assertIn(
            "stage_group", match_pool1_data, "stage_group field missing from match"
        )
        self.assertEqual(
            match_pool1_data["stage_group"],
            pool1.pk,
            "Match pool 1 stage_group ID incorrect",
        )

        self.assertIn(
            "stage_group", match_pool2_data, "stage_group field missing from match"
        )
        self.assertEqual(
            match_pool2_data["stage_group"],
            pool2.pk,
            "Match pool 2 stage_group ID incorrect",
        )

        # Validate ladder summaries have stage_group field
        ladder_summaries = stage_data["ladder_summary"]

        ladder_pool1_team1_data = None
        ladder_pool1_team2_data = None

        for ladder in ladder_summaries:
            if ladder["team"] == team_pool1_1.pk:
                ladder_pool1_team1_data = ladder
            elif ladder["team"] == team_pool1_2.pk:
                ladder_pool1_team2_data = ladder

        self.assertIsNotNone(
            ladder_pool1_team1_data, "Ladder entry for pool 1 team 1 not found"
        )
        self.assertIsNotNone(
            ladder_pool1_team2_data, "Ladder entry for pool 1 team 2 not found"
        )

        self.assertIn(
            "stage_group",
            ladder_pool1_team1_data,
            "stage_group field missing from ladder summary",
        )
        self.assertEqual(
            ladder_pool1_team1_data["stage_group"],
            pool1.pk,
            "Ladder pool 1 stage_group ID incorrect",
        )

        self.assertIn(
            "stage_group",
            ladder_pool1_team2_data,
            "stage_group field missing from ladder summary",
        )
        self.assertEqual(
            ladder_pool1_team2_data["stage_group"],
            pool1.pk,
            "Ladder pool 1 stage_group ID incorrect",
        )

    def test_stage_detail_with_pools(self):
        """Test that stage detail endpoint also exposes pools correctly"""
        # Create a stage with pools
        stage_with_pools = factories.StageFactory.create(division__season=self.season)

        # Create stage groups (pools)
        pool1 = factories.StageGroupFactory.create(
            stage=stage_with_pools, title="Pool A"
        )
        pool2 = factories.StageGroupFactory.create(
            stage=stage_with_pools, title="Pool B"
        )

        # Test stage detail endpoint
        self.get(
            "v1:stage-detail",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            division_slug=stage_with_pools.division.slug,
            slug=stage_with_pools.slug,
        )
        self.response_200()

        response_data = self.last_response.json()

        # Validate pools are exposed
        self.assertIn("pools", response_data, "pools field missing from stage detail")
        pools = response_data["pools"]
        self.assertEqual(len(pools), 2, f"Expected 2 pools, got {len(pools)}")

        # Validate pool structure
        pool_ids = [pool["id"] for pool in pools]
        pool_titles = [pool["title"] for pool in pools]
        self.assertIn(pool1.pk, pool_ids, "Pool 1 ID not found in stage detail pools")
        self.assertIn(pool2.pk, pool_ids, "Pool 2 ID not found in stage detail pools")
        self.assertIn("Pool A", pool_titles, "Pool A title not found in stage detail")
        self.assertIn("Pool B", pool_titles, "Pool B title not found in stage detail")

    def test_matches_and_ladders_without_pools(self):
        """Test that matches and ladder summaries without stage groups return null for stage_group field"""
        # Use existing stage without pools
        stage = self.stage

        # Create a match without stage_group
        match_no_pool = factories.MatchFactory.create(
            stage=stage,
            stage_group=None,  # Explicitly no pool
            home_team=self.team1,
            away_team=self.team2,
            play_at=self.ground,
        )

        # Create ladder summary without stage_group
        factories.LadderSummaryFactory.create(
            stage=stage,
            stage_group=None,  # Explicitly no pool
            team=self.team1,
        )

        # Test division detail endpoint
        self.get(
            "v1:division-detail",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            slug=stage.division.slug,
        )
        self.response_200()

        response_data = self.last_response.json()

        # Find our stage in the response
        stage_data = None
        for stage_item in response_data["stages"]:
            if stage_item["slug"] == stage.slug:
                stage_data = stage_item
                break

        self.assertIsNotNone(stage_data, "Stage not found in response")

        # Check that pools field exists and is empty
        self.assertIn("pools", stage_data, "pools field missing from stage data")
        self.assertEqual(
            stage_data["pools"], [], "Expected empty pools list for stage without pools"
        )

        # Find our match and verify stage_group is null
        match_data = None
        for match in stage_data["matches"]:
            if match["id"] == match_no_pool.id:
                match_data = match
                break

        self.assertIsNotNone(match_data, "Match without pool not found")
        self.assertIn("stage_group", match_data, "stage_group field missing from match")
        self.assertIsNone(
            match_data["stage_group"],
            "Expected null stage_group for match without pool",
        )

        # Find our ladder summary and verify stage_group is null
        ladder_data = None
        for ladder in stage_data["ladder_summary"]:
            if ladder["team"] == self.team1.pk:
                ladder_data = ladder
                break

        self.assertIsNotNone(ladder_data, "Ladder summary without pool not found")
        self.assertIn(
            "stage_group", ladder_data, "stage_group field missing from ladder summary"
        )
        self.assertIsNone(
            ladder_data["stage_group"],
            "Expected null stage_group for ladder summary without pool",
        )
