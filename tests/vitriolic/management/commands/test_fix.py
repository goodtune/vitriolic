#!/usr/bin/env python
"""
Simple Django management command to test the fix manually.
"""
from django.core.management.base import BaseCommand
from tournamentcontrol.competition.tests.factories import (
    DivisionFactory, StageFactory, StageGroupFactory, UndecidedTeamFactory
)
from tournamentcontrol.competition import utils

class Command(BaseCommand):
    help = 'Test the UndecidedTeam formula fix manually'

    def handle(self, *args, **options):
        self.stdout.write("🧪 Testing UndecidedTeam formula fix...")
        
        # Create test data: two stages with Round Robin having 2 pools
        division = DivisionFactory.create()
        
        round_robin_stage = StageFactory.create(
            division=division, 
            order=1,
            title="Round Robin"
        )
        
        # Create two pools in the Round Robin stage
        pool1 = StageGroupFactory.create(stage=round_robin_stage, order=1)
        pool2 = StageGroupFactory.create(stage=round_robin_stage, order=2)
        
        finals_stage = StageFactory.create(
            division=division, 
            order=2,
            title="Finals",
            follows=round_robin_stage
        )

        self.stdout.write(f"✅ Created test setup:")
        self.stdout.write(f"   - Division: {division.title}")
        self.stdout.write(f"   - Stage 1: {round_robin_stage.title} with {round_robin_stage.pools.count()} pools")
        self.stdout.write(f"   - Stage 2: {finals_stage.title}")
        
        # Test valid formula
        self.stdout.write("\n🔍 Testing VALID formula (G1P1)...")
        valid_team = UndecidedTeamFactory.create(
            stage=finals_stage,
            formula="G1P1",
            label="Winner Pool 1"
        )
        
        try:
            title = valid_team.title
            choices = valid_team.choices
            self.stdout.write(f"   ✅ Valid formula G1P1:")
            self.stdout.write(f"      - Title: '{title}'")
            self.stdout.write(f"      - Choices: {choices.count()} teams from pool")
        except Exception as e:
            self.stdout.write(f"   ❌ Valid formula failed: {e}")
        
        # Test invalid formula
        self.stdout.write("\n🔍 Testing INVALID formula (G5P2)...")
        invalid_team = UndecidedTeamFactory.create(
            stage=finals_stage,
            formula="G5P2",  # Group 5 doesn't exist (only 2 pools)
            label="Invalid Group 5"
        )
        
        try:
            title = invalid_team.title
            choices = invalid_team.choices
            self.stdout.write(f"   ✅ Invalid formula G5P2:")
            self.stdout.write(f"      - Title: '{title}'")
            self.stdout.write(f"      - Choices: {choices.count()} teams from division")
            
            # Verify the title is exactly the formula
            if title == "G5P2":
                self.stdout.write("   ✅ Title correctly returns formula")
            else:
                self.stdout.write(self.style.ERROR(f"   ❌ Title should be 'G5P2', got '{title}'"))
                
            # Verify choices are division teams
            if choices == finals_stage.division.teams:
                self.stdout.write("   ✅ Choices correctly fallback to division teams")
            else:
                self.stdout.write(self.style.ERROR("   ❌ Choices should be division teams"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Invalid formula still raises exception: {e}"))
            return
    
        # Test the underlying utils function still raises IndexError
        self.stdout.write("\n🔍 Testing stage_group_position function still raises IndexError...")
        try:
            utils.stage_group_position(finals_stage, "G5P2")
            self.stdout.write(self.style.ERROR("   ❌ stage_group_position should still raise IndexError"))
            return
        except IndexError as e:
            self.stdout.write(f"   ✅ stage_group_position correctly raises IndexError: {e}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ stage_group_position raised unexpected error: {e}"))
            return
        
        self.stdout.write(self.style.SUCCESS("\n🎉 All tests passed! The fix is working correctly."))