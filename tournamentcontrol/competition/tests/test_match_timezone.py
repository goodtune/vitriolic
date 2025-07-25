from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.test import override_settings

from tournamentcontrol.competition.models import Match
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_competition_admin import TestCase


class TimezoneAdjustmentTestCase(TestCase):
    """Test timezone handling in Match datetime calculations."""

    def test_match_datetime_calculation_with_venue_timezone(self):
        """Test that Match.datetime is calculated correctly using venue timezone."""
        # Create a season with a default timezone
        season = factories.SeasonFactory.create(timezone=ZoneInfo("UTC"))
        
        # Create a venue with a specific timezone
        venue = factories.VenueFactory.create(
            season=season,
            timezone=ZoneInfo("Australia/Brisbane")  # UTC+10
        )
        
        # Create division, stage, and teams
        division = factories.DivisionFactory.create(season=season)
        stage = factories.StageFactory.create(division=division)
        home_team = factories.TeamFactory.create(division=division)
        away_team = factories.TeamFactory.create(division=division)
        
        # Create a match at the venue
        match = Match(
            stage=stage,
            home_team=home_team,
            away_team=away_team,
            date=date(2024, 1, 15),
            time=time(14, 30),  # 2:30 PM
            play_at=venue
        )
        
        # Test the clean method which calculates datetime
        match.clean()
        
        # Assert that datetime is correctly set with venue timezone
        # 2:30 PM in Brisbane (UTC+10) should be 4:30 AM UTC
        expected_utc = datetime(2024, 1, 15, 4, 30, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(match.datetime, expected_utc)

    def test_match_datetime_calculation_with_ground_timezone(self):
        """Test that Match.datetime is calculated correctly using ground timezone."""
        # Create a season with a default timezone
        season = factories.SeasonFactory.create(timezone=ZoneInfo("UTC"))
        
        # Create a venue
        venue = factories.VenueFactory.create(
            season=season,
            timezone=ZoneInfo("Europe/London")  # UTC+0 (GMT)
        )
        
        # Create a ground with a different timezone than venue
        ground = factories.GroundFactory.create(
            venue=venue,
            timezone=ZoneInfo("Asia/Tokyo")  # UTC+9
        )
        
        # Create division, stage, and teams
        division = factories.DivisionFactory.create(season=season)
        stage = factories.StageFactory.create(division=division)
        home_team = factories.TeamFactory.create(division=division)
        away_team = factories.TeamFactory.create(division=division)
        
        # Create a match at the ground
        match = Match(
            stage=stage,
            home_team=home_team,
            away_team=away_team,
            date=date(2024, 1, 15),
            time=time(18, 0),  # 6:00 PM
            play_at=ground
        )
        
        # Test the clean method which calculates datetime
        match.clean()
        
        # Assert that datetime is correctly set with ground timezone (not venue timezone)
        # 6:00 PM in Tokyo (UTC+9) should be 9:00 AM UTC
        expected_utc = datetime(2024, 1, 15, 9, 0, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(match.datetime, expected_utc)

    def test_match_datetime_fallback_to_season_timezone(self):
        """Test that Match.datetime falls back to season timezone when play_at is None."""
        # Create a season with a specific timezone
        season = factories.SeasonFactory.create(timezone=ZoneInfo("America/New_York"))  # UTC-5
        
        # Create division, stage, and teams
        division = factories.DivisionFactory.create(season=season)
        stage = factories.StageFactory.create(division=division)
        home_team = factories.TeamFactory.create(division=division)
        away_team = factories.TeamFactory.create(division=division)
        
        # Create a match without a venue/ground
        match = Match(
            stage=stage,
            home_team=home_team,
            away_team=away_team,
            date=date(2024, 1, 15),
            time=time(20, 0),  # 8:00 PM
            play_at=None
        )
        
        # Test the clean method which calculates datetime
        match.clean()
        
        # Assert that datetime is correctly set with season timezone
        # 8:00 PM in New York (UTC-5) should be 1:00 AM UTC next day
        expected_utc = datetime(2024, 1, 16, 1, 0, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(match.datetime, expected_utc)

    def test_venue_timezone_change_updates_match_datetime(self):
        """Test that changing venue timezone updates related match datetime values."""
        # Create a season
        season = factories.SeasonFactory.create(timezone=ZoneInfo("UTC"))
        
        # Create a venue with initial timezone
        venue = factories.VenueFactory.create(
            season=season,
            timezone=ZoneInfo("Australia/Brisbane")  # UTC+10
        )
        
        # Create division, stage, teams and match
        division = factories.DivisionFactory.create(season=season)
        stage = factories.StageFactory.create(division=division)
        home_team = factories.TeamFactory.create(division=division)
        away_team = factories.TeamFactory.create(division=division)
        
        match = factories.MatchFactory.create(
            stage=stage,
            home_team=home_team,
            away_team=away_team,
            date=date(2024, 1, 15),
            time=time(14, 30),  # 2:30 PM
            play_at=venue
        )
        
        # Ensure datetime is calculated with initial timezone
        match.clean()
        match.save()
        
        # 2:30 PM in Brisbane (UTC+10) should be 4:30 AM UTC
        expected_utc_before = datetime(2024, 1, 15, 4, 30, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(match.datetime, expected_utc_before)
        
        # Update venue timezone
        venue.timezone = ZoneInfo("America/New_York")  # UTC-5 (EST)
        venue.save()
        
        # Refresh match from database
        match.refresh_from_db()
        
        # Match datetime should be updated to reflect new timezone
        # 2:30 PM in New York (UTC-5) should be 7:30 PM UTC
        expected_utc_after = datetime(2024, 1, 15, 19, 30, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(match.datetime, expected_utc_after)

    def test_ground_timezone_change_updates_match_datetime(self):
        """Test that changing ground timezone updates related match datetime values."""
        # Create a season and venue
        season = factories.SeasonFactory.create(timezone=ZoneInfo("UTC"))
        venue = factories.VenueFactory.create(
            season=season,
            timezone=ZoneInfo("Europe/London")  # UTC+0 (GMT)
        )
        
        # Create a ground with initial timezone
        ground = factories.GroundFactory.create(
            venue=venue,
            timezone=ZoneInfo("Asia/Tokyo")  # UTC+9
        )
        
        # Create division, stage, teams and match
        division = factories.DivisionFactory.create(season=season)
        stage = factories.StageFactory.create(division=division)
        home_team = factories.TeamFactory.create(division=division)
        away_team = factories.TeamFactory.create(division=division)
        
        match = factories.MatchFactory.create(
            stage=stage,
            home_team=home_team,
            away_team=away_team,
            date=date(2024, 1, 15),
            time=time(18, 0),  # 6:00 PM
            play_at=ground
        )
        
        # Ensure datetime is calculated with initial timezone
        match.clean()
        match.save()
        
        # 6:00 PM in Tokyo (UTC+9) should be 9:00 AM UTC
        expected_utc_before = datetime(2024, 1, 15, 9, 0, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(match.datetime, expected_utc_before)
        
        # Update ground timezone
        ground.timezone = ZoneInfo("Australia/Sydney")  # UTC+11 (AEDT)
        ground.save()
        
        # Refresh match from database
        match.refresh_from_db()
        
        # Match datetime should be updated to reflect new timezone
        # 6:00 PM in Sydney (UTC+11) should be 7:00 AM UTC
        expected_utc_after = datetime(2024, 1, 15, 7, 0, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(match.datetime, expected_utc_after)