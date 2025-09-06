"""
Test to verify the fix for the GROUP BY issue in Division.ladders() method.
"""

from django.test import TestCase
from django.db import connection

from tournamentcontrol.competition.tests.factories import (
    SuperUserFactory, DivisionFactory, StageFactory, StageGroupFactory
)


class DivisionLaddersGroupByTestCase(TestCase):
    """Test that Division.ladders() works correctly with PostgreSQL."""
    
    def setUp(self):
        """Set up test data."""
        self.user = SuperUserFactory.create()
        
        # Create test division with related objects using factories
        self.division = DivisionFactory.create()
        
        # Create a stage that will be included in ladders (keep_ladder=True is default)
        self.stage = StageFactory.create(
            title="Test Stage",
            division=self.division,
            keep_ladder=True
        )
        
        # Create some pools to test pool_count functionality
        self.pool1 = StageGroupFactory.create(
            title="Pool A",
            stage=self.stage
        )
        
        self.pool2 = StageGroupFactory.create(
            title="Pool B", 
            stage=self.stage
        )
    
    def test_division_ladders_no_group_by_error(self):
        """Test that Division.ladders() doesn't cause GROUP BY error."""
        
        # This should work without any GROUP BY errors
        ladders = self.division.ladders()
        
        # Verify the expected stage is present
        stage_slugs = [stage.slug for stage in ladders.keys()]
        self.assertEqual(stage_slugs, [self.stage.slug])
        
        # Verify stage attributes and pool_count
        stage = list(ladders.keys())[0]
        self.assertEqual(stage.title, "Test Stage")
        self.assertEqual(stage.pool_count, 2)
    
    def test_division_ladders_with_no_pools(self):
        """Test Division.ladders() works with stages that have no pools."""
        
        # Create a stage with no pools
        stage_no_pools = StageFactory.create(
            title="Stage No Pools",
            division=self.division,
            keep_ladder=True
        )
        
        # Should work without errors
        ladders = self.division.ladders()
        
        # Should have both stages
        expected_stage_slugs = [self.stage.slug, stage_no_pools.slug]
        actual_stage_slugs = [stage.slug for stage in ladders.keys()]
        self.assertCountEqual(actual_stage_slugs, expected_stage_slugs)
        
        # Verify pool counts for each stage
        stage_pool_counts = {stage.slug: stage.pool_count for stage in ladders.keys()}
        self.assertEqual(stage_pool_counts[self.stage.slug], 2)
        self.assertEqual(stage_pool_counts[stage_no_pools.slug], 0)
    
    def test_division_ladders_excludes_non_ladder_stages(self):
        """Test that stages with keep_ladder=False are excluded."""
        
        # Create a stage that shouldn't keep ladder
        StageFactory.create(
            title="Non Ladder Stage",
            division=self.division,
            keep_ladder=False
        )
        
        # Should only include the ladder-keeping stage
        ladders = self.division.ladders()
        
        # Verify only the expected stage is present
        stage_slugs = [stage.slug for stage in ladders.keys()]
        self.assertEqual(stage_slugs, [self.stage.slug])
    
    def test_stage_pool_count_attribute_preserved(self):
        """Test that the pool_count attribute is properly set on stage objects."""
        
        # Call ladders to set pool_count
        ladders = self.division.ladders()
        stage = list(ladders.keys())[0]
        
        # Verify pool_count matches the actual pool count
        self.assertEqual(stage.pool_count, stage.pools.count())
    
    def test_database_backend_info(self):
        """Log database backend information for debugging."""
        
        # This helps understand which database backend we're testing with
        print(f"\nTesting with database backend: {connection.vendor}")
        print(f"Database name: {connection.settings_dict['NAME']}")
        
        # Run the ladders method to ensure it works
        ladders = self.division.ladders()
        
        # Verify we get the expected stage back
        stage_slugs = [stage.slug for stage in ladders.keys()]
        self.assertEqual(stage_slugs, [self.stage.slug])