from test_plus import TestCase

from tournamentcontrol.competition.constants import ClubStatus
from tournamentcontrol.competition.tests import factories


class ClubStatusTests(TestCase):
    """Test the status field functionality of the Club model"""

    def test_club_default_status_is_active(self):
        """Test that new clubs have active status by default"""
        club = factories.ClubFactory.create()
        self.assertEqual(club.status, ClubStatus.ACTIVE)

    def test_club_status_choices(self):
        """Test that all status choices work correctly"""
        club = factories.ClubFactory.create()
        
        # Test setting to inactive
        club.status = ClubStatus.INACTIVE
        club.save()
        club.refresh_from_db()
        self.assertEqual(club.status, ClubStatus.INACTIVE)
        
        # Test setting to hidden
        club.status = ClubStatus.HIDDEN
        club.save()
        club.refresh_from_db()
        self.assertEqual(club.status, ClubStatus.HIDDEN)
        
        # Test setting back to active
        club.status = ClubStatus.ACTIVE
        club.save()
        club.refresh_from_db()
        self.assertEqual(club.status, ClubStatus.ACTIVE)

    def test_club_status_field_is_indexed(self):
        """Test that the status field has a database index"""
        from django.db import connection
        
        # Get the Club model's database table name
        from tournamentcontrol.competition.models import Club
        table_name = Club._meta.db_table
        
        # Check if there's an index on the status field
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = '{table_name}' 
                AND indexdef LIKE '%status%'
            """)
            indexes = cursor.fetchall()
        
        # There should be at least one index on the status field
        self.assertTrue(len(indexes) > 0, "No index found on status field")

    def test_club_status_string_representation(self):
        """Test that status values have proper string representations"""
        self.assertEqual(ClubStatus.ACTIVE.label, "Active")
        self.assertEqual(ClubStatus.INACTIVE.label, "Inactive")
        self.assertEqual(ClubStatus.HIDDEN.label, "Hidden")
        
        # Test the values
        self.assertEqual(ClubStatus.ACTIVE.value, "active")
        self.assertEqual(ClubStatus.INACTIVE.value, "inactive")
        self.assertEqual(ClubStatus.HIDDEN.value, "hidden")