"""
Test to verify the fix for the GROUP BY issue in Division.ladders() method.
"""

from django.test import TestCase
from django.db import connection

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.models import Competition, Season, Division, Stage, StageGroup


class DivisionLaddersGroupByTestCase(TestCase):
    """Test that Division.ladders() works correctly with PostgreSQL."""
    
    def setUp(self):
        """Set up test data."""
        self.user = UserFactory(is_superuser=True)
        
        # Create test competition structure
        self.competition = Competition.objects.create(
            title="Test Competition",
            slug="test-comp",
            enabled=True
        )
        
        self.season = Season.objects.create(
            title="Test Season",
            slug="test-season",
            competition=self.competition
        )
        
        self.division = Division.objects.create(
            title="Test Division",
            slug="test-div",
            season=self.season,
            order=1
        )
        
        # Create a stage that will be included in ladders (keep_ladder=True is default)
        self.stage = Stage.objects.create(
            title="Test Stage",
            slug="test-stage",
            division=self.division,
            order=1,
            keep_ladder=True
        )
        
        # Create some pools to test pool_count functionality
        self.pool1 = StageGroup.objects.create(
            title="Pool A",
            slug="pool-a",
            stage=self.stage,
            order=1
        )
        
        self.pool2 = StageGroup.objects.create(
            title="Pool B",
            slug="pool-b",
            stage=self.stage,
            order=2
        )
    
    def test_division_ladders_no_group_by_error(self):
        """Test that Division.ladders() doesn't cause GROUP BY error."""
        
        # This should work without any GROUP BY errors
        ladders = self.division.ladders()
        
        # Verify the result is as expected
        self.assertIsInstance(ladders, dict)
        self.assertEqual(len(ladders), 1)  # One stage
        
        # Verify we can access stage attributes without error
        for stage, pools in ladders.items():
            self.assertEqual(stage.title, "Test Stage")
            self.assertEqual(stage.slug, "test-stage")
            # Verify pool_count is correctly calculated
            self.assertEqual(stage.pool_count, 2)
    
    def test_division_ladders_with_no_pools(self):
        """Test Division.ladders() works with stages that have no pools."""
        
        # Create a stage with no pools
        stage_no_pools = Stage.objects.create(
            title="Stage No Pools",
            slug="stage-no-pools",
            division=self.division,
            order=2,
            keep_ladder=True
        )
        
        # Should work without errors
        ladders = self.division.ladders()
        
        # Should have both stages
        self.assertEqual(len(ladders), 2)
        
        stage_pool_counts = {stage.slug: stage.pool_count for stage in ladders.keys()}
        self.assertEqual(stage_pool_counts["test-stage"], 2)
        self.assertEqual(stage_pool_counts["stage-no-pools"], 0)
    
    def test_division_ladders_excludes_non_ladder_stages(self):
        """Test that stages with keep_ladder=False are excluded."""
        
        # Create a stage that shouldn't keep ladder
        Stage.objects.create(
            title="Non Ladder Stage",
            slug="non-ladder-stage",
            division=self.division,
            order=3,
            keep_ladder=False
        )
        
        # Should only include the ladder-keeping stage
        ladders = self.division.ladders()
        self.assertEqual(len(ladders), 1)
        
        stage = list(ladders.keys())[0]
        self.assertEqual(stage.slug, "test-stage")
    
    def test_stage_pool_count_attribute_preserved(self):
        """Test that the pool_count attribute is properly set on stage objects."""
        
        # Call ladders to set pool_count
        ladders = self.division.ladders()
        stage = list(ladders.keys())[0]
        
        # Verify pool_count is set correctly
        self.assertTrue(hasattr(stage, 'pool_count'))
        self.assertEqual(stage.pool_count, 2)
        
        # Verify it matches the actual pool count
        self.assertEqual(stage.pool_count, stage.pools.count())
    
    def test_database_backend_info(self):
        """Log database backend information for debugging."""
        
        # This helps understand which database backend we're testing with
        print(f"\nTesting with database backend: {connection.vendor}")
        print(f"Database name: {connection.settings_dict['NAME']}")
        
        # Run the ladders method to ensure it works
        ladders = self.division.ladders()
        self.assertIsInstance(ladders, dict)