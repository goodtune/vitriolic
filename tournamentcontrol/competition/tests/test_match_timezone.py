from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from tournamentcontrol.competition.models import Match
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_competition_admin import TestCase


class TimezoneAdjustmentTestCase(TestCase):
    """Test timezone handling in Match datetime calculations."""

    def setUp(self):
        """Set up common test data."""
        self.season = factories.SeasonFactory.create(timezone=ZoneInfo("UTC"))
        self.division = factories.DivisionFactory.create(season=self.season)
        self.stage = factories.StageFactory.create(division=self.division)
        self.home_team = factories.TeamFactory.create(division=self.division)
        self.away_team = factories.TeamFactory.create(division=self.division)

    def test_match_datetime_calculation_scenarios(self):
        """Test Match.datetime calculation with different timezone scenarios."""

        scenarios = [
            {
                "name": "venue_timezone",
                "description": "venue timezone (Australia/Brisbane UTC+10)",
                "setup": lambda: factories.VenueFactory.create(
                    season=self.season, timezone=ZoneInfo("Australia/Brisbane")
                ),
                "date": date(2024, 1, 15),
                "time": time(14, 30),  # 2:30 PM
                "expected_utc": datetime(2024, 1, 15, 4, 30, tzinfo=ZoneInfo("UTC")),
            },
            {
                "name": "ground_timezone",
                "description": "ground timezone (Asia/Tokyo UTC+9) overriding venue (Europe/London UTC+0)",
                "setup": lambda: factories.GroundFactory.create(
                    venue=factories.VenueFactory.create(
                        season=self.season, timezone=ZoneInfo("Europe/London")
                    ),
                    timezone=ZoneInfo("Asia/Tokyo"),
                ),
                "date": date(2024, 1, 15),
                "time": time(18, 0),  # 6:00 PM
                "expected_utc": datetime(2024, 1, 15, 9, 0, tzinfo=ZoneInfo("UTC")),
            },
            {
                "name": "season_timezone_fallback",
                "description": "season timezone fallback (America/New_York UTC-5) when no play_at",
                "setup": lambda: None,
                "season_timezone": ZoneInfo("America/New_York"),
                "date": date(2024, 1, 15),
                "time": time(20, 0),  # 8:00 PM
                "expected_utc": datetime(2024, 1, 16, 1, 0, tzinfo=ZoneInfo("UTC")),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario=scenario["name"]):
                # Set up season timezone if specified
                if "season_timezone" in scenario:
                    season = factories.SeasonFactory.create(
                        timezone=scenario["season_timezone"]
                    )
                    division = factories.DivisionFactory.create(season=season)
                    stage = factories.StageFactory.create(division=division)
                    home_team = factories.TeamFactory.create(division=division)
                    away_team = factories.TeamFactory.create(division=division)
                else:
                    season = self.season
                    stage = self.stage
                    home_team = self.home_team
                    away_team = self.away_team

                # Set up the play_at location
                play_at = scenario["setup"]()

                # Create match
                match = Match(
                    stage=stage,
                    home_team=home_team,
                    away_team=away_team,
                    date=scenario["date"],
                    time=scenario["time"],
                    play_at=play_at,
                )

                # Test datetime calculation
                match.clean()

                # Assert correct timezone calculation
                self.assertEqual(
                    match.datetime,
                    scenario["expected_utc"],
                    f"Failed for {scenario['description']}",
                )

    def test_timezone_change_updates_match_datetime_scenarios(self):
        """Test that timezone changes update related match datetime values."""

        scenarios = [
            {
                "name": "venue_timezone_change",
                "description": "venue timezone change from Australia/Brisbane to America/New_York",
                "setup": lambda: factories.VenueFactory.create(
                    season=self.season, timezone=ZoneInfo("Australia/Brisbane")
                ),
                "initial_timezone": ZoneInfo("Australia/Brisbane"),  # UTC+10
                "new_timezone": ZoneInfo("America/New_York"),  # UTC-5
                "date": date(2024, 1, 15),
                "time": time(14, 30),  # 2:30 PM
                "expected_utc_before": datetime(
                    2024, 1, 15, 4, 30, tzinfo=ZoneInfo("UTC")
                ),
                "expected_utc_after": datetime(
                    2024, 1, 15, 19, 30, tzinfo=ZoneInfo("UTC")
                ),
            },
            {
                "name": "ground_timezone_change",
                "description": "ground timezone change from Asia/Tokyo to Australia/Sydney",
                "setup": lambda: factories.GroundFactory.create(
                    venue=factories.VenueFactory.create(
                        season=self.season, timezone=ZoneInfo("Europe/London")
                    ),
                    timezone=ZoneInfo("Asia/Tokyo"),
                ),
                "initial_timezone": ZoneInfo("Asia/Tokyo"),  # UTC+9
                "new_timezone": ZoneInfo("Australia/Sydney"),  # UTC+11
                "date": date(2024, 1, 15),
                "time": time(18, 0),  # 6:00 PM
                "expected_utc_before": datetime(
                    2024, 1, 15, 9, 0, tzinfo=ZoneInfo("UTC")
                ),
                "expected_utc_after": datetime(
                    2024, 1, 15, 7, 0, tzinfo=ZoneInfo("UTC")
                ),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario=scenario["name"]):
                # Set up the place (venue or ground)
                place = scenario["setup"]()

                # Create match
                match = factories.MatchFactory.create(
                    stage=self.stage,
                    home_team=self.home_team,
                    away_team=self.away_team,
                    date=scenario["date"],
                    time=scenario["time"],
                    play_at=place,
                )

                # Ensure datetime is calculated with initial timezone
                match.clean()
                match.save()

                # Verify initial datetime
                self.assertEqual(
                    match.datetime,
                    scenario["expected_utc_before"],
                    f"Initial datetime incorrect for {scenario['description']}",
                )

                # Update timezone - this should trigger the signal automatically
                place.timezone = scenario["new_timezone"]
                place.save()

                # Refresh match from database
                match.refresh_from_db()

                # Verify updated datetime
                self.assertEqual(
                    match.datetime,
                    scenario["expected_utc_after"],
                    f"Updated datetime incorrect for {scenario['description']}",
                )
