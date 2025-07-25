from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from tournamentcontrol.competition.models import Match
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_competition_admin import TestCase


class TimezoneAdjustmentTestCase(TestCase):
    """Test that adjusting timezone on Venue or Ground forces related Match.datetime values to be reevaluated."""

    def test_venue_timezone_adjustment_updates_match_datetime(self):
        """Test that updating a Venue timezone via edit_venue view updates related Match.datetime values."""
        with self.subTest("Venue timezone adjustment"):
            # Create a season with initial timezone
            season = factories.SeasonFactory.create(timezone=ZoneInfo("UTC"))
            
            # Create a venue with initial timezone
            venue = factories.VenueFactory.create(
                season=season,
                timezone=ZoneInfo("Australia/Brisbane")  # UTC+10
            )
            
            # Create a division and stage
            division = factories.DivisionFactory.create(season=season)
            stage = factories.StageFactory.create(division=division)
            
            # Create teams
            home_team = factories.TeamFactory.create(division=division)
            away_team = factories.TeamFactory.create(division=division)
            
            # Create a match at the venue
            match = factories.MatchFactory.create(
                stage=stage,
                home_team=home_team,
                away_team=away_team,
                date=date(2024, 1, 15),
                time=time(14, 30),  # 2:30 PM
                play_at=venue
            )
            
            # Force clean to calculate datetime
            match.clean()
            match.save()
            
            # Assert that datetime is correctly set with initial timezone
            # 2:30 PM in Brisbane (UTC+10) should be 4:30 AM UTC
            expected_utc = datetime(2024, 1, 15, 4, 30, tzinfo=ZoneInfo("UTC"))
            self.assertEqual(match.datetime, expected_utc)
            
            # Update venue timezone using edit_venue view
            new_timezone = ZoneInfo("America/New_York")  # UTC-5 (EST)
            venue_edit_url = venue.urls["edit"]
            
            venue_data = {
                'title': venue.title,
                'short_title': venue.short_title,
                'abbreviation': venue.abbreviation,
                'timezone': 'America/New_York',
                'latlng': venue.latlng,
                'slug': venue.slug,
                'slug_locked': venue.slug_locked,
            }
            
            with self.login(self.superuser):
                response = self.post(venue_edit_url, **venue_data)
                self.response_302(response)
            
            # Refresh match from database
            match.refresh_from_db()
            
            # Assert that datetime has been adjusted to new timezone
            # 2:30 PM in New York (UTC-5) should be 7:30 PM UTC  
            expected_utc_after = datetime(2024, 1, 15, 19, 30, tzinfo=ZoneInfo("UTC"))
            self.assertEqual(match.datetime, expected_utc_after)

    def test_ground_timezone_adjustment_updates_match_datetime(self):
        """Test that updating a Ground timezone via edit_ground view updates related Match.datetime values."""
        with self.subTest("Ground timezone adjustment"):
            # Create a season with initial timezone
            season = factories.SeasonFactory.create(timezone=ZoneInfo("UTC"))
            
            # Create a venue
            venue = factories.VenueFactory.create(
                season=season,
                timezone=ZoneInfo("Europe/London")  # UTC+0 (GMT)
            )
            
            # Create a ground with initial timezone  
            ground = factories.GroundFactory.create(
                venue=venue,
                timezone=ZoneInfo("Asia/Tokyo")  # UTC+9
            )
            
            # Create a division and stage
            division = factories.DivisionFactory.create(season=season)
            stage = factories.StageFactory.create(division=division)
            
            # Create teams
            home_team = factories.TeamFactory.create(division=division)
            away_team = factories.TeamFactory.create(division=division)
            
            # Create a match at the ground
            match = factories.MatchFactory.create(
                stage=stage,
                home_team=home_team,
                away_team=away_team,
                date=date(2024, 1, 15),
                time=time(18, 0),  # 6:00 PM
                play_at=ground
            )
            
            # Force clean to calculate datetime
            match.clean()
            match.save()
            
            # Assert that datetime is correctly set with initial timezone
            # 6:00 PM in Tokyo (UTC+9) should be 9:00 AM UTC
            expected_utc = datetime(2024, 1, 15, 9, 0, tzinfo=ZoneInfo("UTC"))
            self.assertEqual(match.datetime, expected_utc)
            
            # Update ground timezone using edit_ground view
            ground_edit_url = ground.urls["edit"]
            
            ground_data = {
                'title': ground.title,
                'short_title': ground.short_title,
                'abbreviation': ground.abbreviation,
                'timezone': 'Australia/Sydney',  # UTC+11 (AEDT)
                'latlng': ground.latlng,
                'slug': ground.slug,
                'slug_locked': ground.slug_locked,
                'live_stream': ground.live_stream,
            }
            
            with self.login(self.superuser):
                response = self.post(ground_edit_url, **ground_data)
                self.response_302(response)
            
            # Refresh match from database
            match.refresh_from_db()
            
            # Assert that datetime has been adjusted to new timezone
            # 6:00 PM in Sydney (UTC+11) should be 7:00 AM UTC
            expected_utc_after = datetime(2024, 1, 15, 7, 0, tzinfo=ZoneInfo("UTC"))
            self.assertEqual(match.datetime, expected_utc_after)