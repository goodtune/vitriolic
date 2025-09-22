from django.test.utils import override_settings
from test_plus import TestCase

from tournamentcontrol.competition.constants import ClubStatus
from tournamentcontrol.competition.draw import schemas
from tournamentcontrol.competition.draw.builders import build
from tournamentcontrol.competition.models import Club, LadderSummary
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.utils import round_robin_format


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
            round=1,
        )

    def test_club_list(self):
        """Test club-list endpoint"""
        self.get("v1:competition:club-list")
        self.response_200()

    def test_club_detail(self):
        """Test club-detail endpoint"""
        self.get("v1:competition:club-detail", slug=self.club.slug)
        self.response_200()

        response_data = self.last_response.json()
        self.assertEqual(response_data["status"], "active")

    def test_clubs_api_with_different_statuses(self):
        """Test that club-list endpoint includes status field for clubs with different statuses"""
        factories.ClubFactory.create(status=ClubStatus.INACTIVE)
        factories.ClubFactory.create(status=ClubStatus.HIDDEN)

        self.get("v1:competition:club-list")
        self.response_200()

        # Build expected payload for all clubs ordered by title
        expected_payload = [
            {
                "title": club.title,
                "short_title": club.short_title,
                "slug": club.slug,
                "abbreviation": club.abbreviation,
                "status": club.status,
                "url": f"http://testserver/api/v1/clubs/{club.slug}/",
                "facebook": club.facebook,
                "twitter": club.twitter,
                "youtube": club.youtube,
                "website": club.website,
            }
            for club in Club.objects.all().order_by("title")
        ]

        self.assertJSONEqual(self.last_response.content, expected_payload)

    def test_competition_list(self):
        """Test competition-list endpoint"""
        self.get("v1:competition:competition-list")
        self.response_200()

    def test_competition_detail(self):
        """Test competition-detail endpoint"""
        self.get("v1:competition:competition-detail", slug=self.competition.slug)
        self.response_200()

    def test_season_list(self):
        """Test season-list endpoint"""
        self.get(
            "v1:competition:season-list",
            competition_slug=self.competition.slug,
        )
        self.response_200()

    def test_season_detail(self):
        """Test season-detail endpoint"""
        self.get(
            "v1:competition:season-detail",
            competition_slug=self.competition.slug,
            slug=self.season.slug,
        )
        self.response_200()

    def test_division_list(self):
        """Test division-list endpoint"""
        self.get(
            "v1:competition:division-list",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
        )
        self.response_200()

    def test_division_detail(self):
        """Test division-detail endpoint"""
        self.get(
            "v1:competition:division-detail",
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
                            "status": "active",
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
                            "status": "active",
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
                        "pools": [],
                        "matches": [
                            {
                                "id": self.match.id,
                                "uuid": str(self.match.uuid),
                                "round": "Round 1",
                                "stage_group": None,
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


    def test_stage_list(self):
        """Test stage-list endpoint"""
        self.get(
            "v1:competition:stage-list",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            division_slug=self.division.slug,
        )
        self.response_200()

    def test_stage_detail(self):
        """Test stage-detail endpoint"""
        self.get(
            "v1:competition:stage-detail",
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
            "v1:competition:division-detail",
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
                        "status": "active",
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
                        "status": "active",
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
                    "pools": [],
                    "matches": [
                        {
                            "id": match1.id,
                            "uuid": str(match1.uuid),
                            "round": "Round 1",
                            "stage_group": None,
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
                                "abbreviation": None,
                                "timezone": str(self.ground.timezone),
                            },
                        },
                        {
                            "id": match2.id,
                            "uuid": str(match2.uuid),
                            "round": "Round 2",
                            "stage_group": None,
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
                                "abbreviation": None,
                                "timezone": str(self.ground.timezone),
                            },
                        },
                        {
                            "id": match3.id,
                            "uuid": str(match3.uuid),
                            "round": "Round 3",
                            "stage_group": None,
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
                                "abbreviation": None,
                                "timezone": str(self.ground.timezone),
                            },
                        },
                    ],
                    "ladder_summary": [
                        {
                            "team": match1.home_team.id,
                            "stage_group": None,
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
                            "stage_group": None,
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
        # Define a division structure with pools and ladder summaries
        spec = schemas.DivisionStructure(
            title="Pool Tournament",
            teams=["Alpha", "Beta", "Gamma", "Delta"],
            draw_formats={
                "single_match": round_robin_format(2),
            },
            stages=[
                schemas.StageFixture(
                    title="Pool Round",
                    pools=[
                        schemas.PoolFixture(
                            title="Pool A",
                            teams=[0, 1],  # Alpha, Beta
                            draw_format_ref="single_match",
                        ),
                        schemas.PoolFixture(
                            title="Pool B",
                            teams=[2, 3],  # Gamma, Delta
                            draw_format_ref="single_match",
                        ),
                    ],
                )
            ],
        )

        # Build the division structure
        division = build(self.season, spec)

        # FIXME: we don't have this in the structure, and we normally
        #        rely on the DivisionFactory to populate it.
        division.points_formula = "3*win + 2*draw + 1*loss"
        division.save()

        stage = division.stages.first()

        # Score matches to trigger ladder summary generation via signals
        for match in stage.matches.all():
            match.home_team_score = 50
            match.away_team_score = 40
            match.date = "2025-08-22"
            match.time = "09:00:00"
            match.datetime = "2025-08-22T09:00:00.000000Z"
            match.play_at = self.ground
            match.save()

        self.assertQuerySetEqual(
            LadderSummary.objects.all(),
            [
                "<LadderSummary: Pool Round - Pool A - Alpha>",
                "<LadderSummary: Pool Round - Pool B - Gamma>",
                "<LadderSummary: Pool Round - Pool A - Beta>",
                "<LadderSummary: Pool Round - Pool B - Delta>",
            ],
            transform=repr,
        )

        # Test division detail endpoint
        self.get(
            "v1:competition:division-detail",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            slug=division.slug,
        )
        self.response_200()

        # Look up objects by title using get()
        alpha = division.teams.get(title="Alpha")
        beta = division.teams.get(title="Beta")
        gamma = division.teams.get(title="Gamma")
        delta = division.teams.get(title="Delta")

        pool_a = stage.pools.get(title="Pool A")
        pool_b = stage.pools.get(title="Pool B")

        # Get matches by team participation
        matches = list(stage.matches.all())
        alpha_beta_match = next(
            m for m in matches if (m.home_team == alpha and m.away_team == beta)
        )
        gamma_delta_match = next(
            m for m in matches if (m.home_team == gamma and m.away_team == delta)
        )

        # Fully static expected payload with looked-up IDs
        expected_payload = {
            "title": "Pool Tournament",
            "slug": "pool-tournament",
            "url": f"http://testserver/api/v1/competitions/{self.competition.slug}/seasons/{self.season.slug}/divisions/pool-tournament/",
            "teams": [
                {
                    "id": alpha.id,
                    "title": "Alpha",
                    "slug": "alpha",
                    "club": None,
                },
                {
                    "id": beta.id,
                    "title": "Beta",
                    "slug": "beta",
                    "club": None,
                },
                {
                    "id": gamma.id,
                    "title": "Gamma",
                    "slug": "gamma",
                    "club": None,
                },
                {
                    "id": delta.id,
                    "title": "Delta",
                    "slug": "delta",
                    "club": None,
                },
            ],
            "stages": [
                {
                    "title": "Pool Round",
                    "slug": "pool-round",
                    "url": f"http://testserver/api/v1/competitions/{self.competition.slug}/seasons/{self.season.slug}/divisions/pool-tournament/stages/pool-round/",
                    "pools": [
                        {
                            "id": pool_a.id,
                            "title": "Pool A",
                        },
                        {
                            "id": pool_b.id,
                            "title": "Pool B",
                        },
                    ],
                    "matches": [
                        {
                            "id": alpha_beta_match.id,
                            "uuid": str(alpha_beta_match.uuid),
                            "round": "Round 1",
                            "date": "2025-08-22",
                            "time": "09:00:00",
                            "datetime": "2025-08-22T09:00:00Z",
                            "is_bye": False,
                            "is_washout": False,
                            "home_team": alpha.id,
                            "home_team_score": 50,
                            "away_team": beta.id,
                            "away_team_score": 40,
                            "stage_group": pool_a.id,
                            "referees": [],
                            "videos": None,
                            "play_at": {
                                "id": self.ground.id,
                                "title": self.ground.title,
                                "abbreviation": None,
                                "timezone": str(self.ground.timezone),
                            },
                        },
                        {
                            "id": gamma_delta_match.id,
                            "uuid": str(gamma_delta_match.uuid),
                            "round": "Round 1",
                            "date": "2025-08-22",
                            "time": "09:00:00",
                            "datetime": "2025-08-22T09:00:00Z",
                            "is_bye": False,
                            "is_washout": False,
                            "home_team": gamma.id,
                            "home_team_score": 50,
                            "away_team": delta.id,
                            "away_team_score": 40,
                            "stage_group": pool_b.id,
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
                    "ladder_summary": [
                        {
                            "team": alpha.id,  # Alpha - winner Pool A
                            "stage_group": pool_a.id,
                            "played": 1,
                            "win": 1,
                            "loss": 0,
                            "draw": 0,
                            "bye": 0,
                            "forfeit_for": 0,
                            "forfeit_against": 0,
                            "score_for": 50,
                            "score_against": 40,
                            "difference": "10.000",
                            "percentage": "125.00",
                            "points": "3.000",
                            "bonus_points": 0,
                        },
                        {
                            "team": gamma.id,  # Gamma - winner Pool B
                            "stage_group": pool_b.id,
                            "played": 1,
                            "win": 1,
                            "loss": 0,
                            "draw": 0,
                            "bye": 0,
                            "forfeit_for": 0,
                            "forfeit_against": 0,
                            "score_for": 50,
                            "score_against": 40,
                            "difference": "10.000",
                            "percentage": "125.00",
                            "points": "3.000",
                            "bonus_points": 0,
                        },
                        {
                            "team": beta.id,  # Beta - loser Pool A
                            "stage_group": pool_a.id,
                            "played": 1,
                            "win": 0,
                            "loss": 1,
                            "draw": 0,
                            "bye": 0,
                            "forfeit_for": 0,
                            "forfeit_against": 0,
                            "score_for": 40,
                            "score_against": 50,
                            "difference": "-10.000",
                            "percentage": "80.00",
                            "points": "1.000",
                            "bonus_points": 0,
                        },
                        {
                            "team": delta.id,  # Delta - loser Pool B
                            "stage_group": pool_b.id,
                            "played": 1,
                            "win": 0,
                            "loss": 1,
                            "draw": 0,
                            "bye": 0,
                            "forfeit_for": 0,
                            "forfeit_against": 0,
                            "score_for": 40,
                            "score_against": 50,
                            "difference": "-10.000",
                            "percentage": "80.00",
                            "points": "1.000",
                            "bonus_points": 0,
                        },
                    ],
                }
            ],
        }

        self.assertJSONEqual(self.last_response.content, expected_payload)

    def test_stage_detail_with_pools(self):
        """Test that stage detail endpoint also exposes pools correctly"""
        # Define a division structure with pools
        spec = schemas.DivisionStructure(
            title="Pool Competition",
            teams=["Team 1", "Team 2", "Team 3", "Team 4"],
            stages=[
                schemas.StageFixture(
                    title="Pool Stage",
                    pools=[
                        schemas.PoolFixture(
                            title="Pool A",
                            teams=[0, 1],  # Team 1, Team 2
                            draw_format_ref="pool_round_robin",
                        ),
                        schemas.PoolFixture(
                            title="Pool B",
                            teams=[2, 3],  # Team 3, Team 4
                            draw_format_ref="pool_round_robin",
                        ),
                    ],
                )
            ],
            draw_formats={"pool_round_robin": "R(1,2)"},
        )

        # Build the division structure
        division = build(self.season, spec)
        stage = division.stages.first()
        pools = list(stage.pools.all())

        # Test stage detail endpoint
        self.get(
            "v1:competition:stage-detail",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            division_slug=division.slug,
            slug=stage.slug,
        )
        self.response_200()

        expected_payload = {
            "title": stage.title,
            "slug": stage.slug,
            "teams": [
                {
                    "id": t.id,
                    "title": t.title,
                    "slug": t.slug,
                    "club": (
                        {
                            "abbreviation": t.club.abbreviation,
                            "facebook": t.club.facebook,
                            "short_title": t.club.short_title,
                            "slug": t.club.slug,
                            "status": "active",
                            "title": t.club.title,
                            "twitter": t.club.twitter,
                            "url": f"http://testserver/api/v1/clubs/{t.club.slug}/",
                            "website": t.club.website,
                            "youtube": t.club.youtube,
                        }
                        if t.club
                        else None
                    ),
                }
                for t in division.teams.all()
            ],
            "matches": [
                {
                    "id": m.id,
                    "uuid": str(m.uuid),
                    "round": m.label or f"Round {m.round}",
                    "date": m.date,
                    "time": m.time,
                    "datetime": m.datetime,
                    "is_bye": m.is_bye,
                    "is_washout": m.is_washout,
                    "home_team": (
                        m.home_team.pk if hasattr(m.home_team, "pk") else m.home_team
                    ),
                    "home_team_score": m.home_team_score,
                    "away_team": (
                        m.away_team.pk if hasattr(m.away_team, "pk") else m.away_team
                    ),
                    "away_team_score": m.away_team_score,
                    "stage_group": m.stage_group.pk if m.stage_group else None,
                    "referees": [],
                    "videos": m.videos,
                    "play_at": (
                        {
                            "id": m.play_at.id,
                            "title": m.play_at.title,
                            "abbreviation": m.play_at.abbreviation,
                            "timezone": str(m.play_at.timezone),
                        }
                        if m.play_at
                        else None
                    ),
                }
                for m in stage.matches.all()
            ],
            "pools": [
                {
                    "id": p.id,
                    "title": p.title,
                }
                for p in pools
            ],
        }

        self.assertJSONEqual(self.last_response.content, expected_payload)

    def test_matches_and_ladders_without_pools(self):
        """Test that matches and ladder summaries without stage groups return null for stage_group field"""
        # Define a simple division structure without pools
        spec = schemas.DivisionStructure(
            title="Test Division",
            teams=["Team A", "Team B", "Team C", "Team D"],
            stages=[
                schemas.StageFixture(
                    title="Round Robin",
                    draw_format_ref="round_robin",
                )
            ],
            draw_formats={"round_robin": "R(1,2,3,4)"},
        )

        # Build the division structure
        division = build(self.season, spec)
        stage = division.stages.first()

        # Get matches from the built structure and add scores to trigger ladder generation
        matches = list(stage.matches.all())
        if matches:
            # Score the first match to trigger ladder summary generation
            match = matches[0]
            match.home_team_score = 100
            match.away_team_score = 80
            match.date = "2025-08-22"
            match.time = "09:00:00"
            match.datetime = "2025-08-22T09:00:00.000000Z"
            match.play_at = self.ground
            match.save()

        # Test division detail endpoint
        self.get(
            "v1:competition:division-detail",
            competition_slug=self.competition.slug,
            season_slug=self.season.slug,
            slug=division.slug,
        )
        self.response_200()

        expected_payload = {
            "title": division.title,
            "slug": division.slug,
            "url": f"http://testserver/api/v1/competitions/{self.competition.slug}/seasons/{self.season.slug}/divisions/{division.slug}/",
            "teams": [
                {
                    "id": t.id,
                    "title": t.title,
                    "slug": t.slug,
                    "club": (
                        {
                            "abbreviation": t.club.abbreviation,
                            "facebook": t.club.facebook,
                            "short_title": t.club.short_title,
                            "slug": t.club.slug,
                            "status": "active",
                            "title": t.club.title,
                            "twitter": t.club.twitter,
                            "url": f"http://testserver/api/v1/clubs/{t.club.slug}/",
                            "website": t.club.website,
                            "youtube": t.club.youtube,
                        }
                        if t.club
                        else None
                    ),
                }
                for t in division.teams.all()
            ],
            "stages": [
                {
                    "title": stage.title,
                    "slug": stage.slug,
                    "url": f"http://testserver/api/v1/competitions/{self.competition.slug}/seasons/{self.season.slug}/divisions/{division.slug}/stages/{stage.slug}/",
                    "pools": [],  # Empty pools for stage without pools
                    "matches": [
                        {
                            "id": m.id,
                            "uuid": str(m.uuid),
                            "round": m.label or f"Round {m.round}",
                            "date": m.date,
                            "time": m.time,
                            "datetime": m.datetime,
                            "is_bye": m.is_bye,
                            "is_washout": m.is_washout,
                            "home_team": (
                                m.home_team.pk
                                if hasattr(m.home_team, "pk")
                                else m.home_team
                            ),
                            "home_team_score": m.home_team_score,
                            "away_team": (
                                m.away_team.pk
                                if hasattr(m.away_team, "pk")
                                else m.away_team
                            ),
                            "away_team_score": m.away_team_score,
                            "stage_group": None,  # No pool
                            "referees": [],
                            "videos": m.videos,
                            "play_at": (
                                {
                                    "id": m.play_at.id,
                                    "title": m.play_at.title,
                                    "abbreviation": m.play_at.abbreviation,
                                    "timezone": str(m.play_at.timezone),
                                }
                                if m.play_at
                                else None
                            ),
                        }
                        for m in stage.matches.all()
                    ],
                    "ladder_summary": [
                        {
                            "team": ls.team.id,
                            "stage_group": None,  # No pool
                            "played": ls.played,
                            "win": ls.win,
                            "loss": ls.loss,
                            "draw": ls.draw,
                            "bye": ls.bye,
                            "forfeit_for": ls.forfeit_for,
                            "forfeit_against": ls.forfeit_against,
                            "score_for": ls.score_for,
                            "score_against": ls.score_against,
                            "difference": str(ls.difference),
                            "percentage": (
                                str(ls.percentage)
                                if ls.percentage is not None
                                else None
                            ),
                            "points": str(ls.points),
                            "bonus_points": ls.bonus_points,
                        }
                        for ls in stage.ladder_summary.all()
                    ],
                }
            ],
        }

        self.assertJSONEqual(self.last_response.content, expected_payload)
