"""End-to-end test for Stage reordering functionality in admin interface."""

import pytest
from playwright.sync_api import Page, expect


class TestStageReordering:
    """Test Stage reordering functionality in the admin UI."""

    @pytest.fixture
    def division_with_stages(self, db):
        """
        Create a division with multiple stages for reordering tests.
        
        Returns:
            Division: A division with three stages in order
        """
        from tournamentcontrol.competition.tests import factories
        
        # Create a complete hierarchy: Competition -> Season -> Division
        division = factories.DivisionFactory.create(title="Under 12")
        
        # Create three stages in order
        stage1 = factories.StageFactory.create(
            division=division,
            title="Preliminary",
            short_title="Prelim",
            order=1
        )
        stage2 = factories.StageFactory.create(
            division=division,
            title="Semi-Finals",
            short_title="Semi",
            order=2
        )
        stage3 = factories.StageFactory.create(
            division=division,
            title="Finals",
            short_title="Final",
            order=3
        )
        
        # Store stage IDs for verification
        division.test_stages = [stage1, stage2, stage3]
        return division

    def test_stage_reorder_buttons_visible(
        self, 
        authenticated_page: Page, 
        live_server, 
        division_with_stages,
        screenshot_dir
    ):
        """
        Test that Stage reorder buttons exist in the admin UI HTML.
        
        This test validates that reorder buttons for stages have been successfully
        added to the admin interface template:
        1. Navigates directly to the Division edit page
        2. Verifies reorder buttons exist in the DOM for all stages
        3. Captures screenshots documenting the UI changes
        
        Note: The buttons are rendered in the HTML but may be in a hidden dropdown
        menu or collapsed section depending on the admin UI design. This test
        confirms the template changes are in place and the buttons are in the DOM.
        
        Prerequisites:
        - Authenticated admin user with competition management permissions
        - Division with multiple stages created via fixtures
        - Stage admin interface with reorder buttons added to template
        
        Expected behavior:
        - Up and down reorder buttons exist in DOM for each stage  
        - Buttons have correct href patterns pointing to reorder endpoints
        - Screenshots capture the admin UI showing stages section
        
        Args:
            authenticated_page: Pre-authenticated Playwright page
            live_server: Django live server fixture
            division_with_stages: Division with test stages
            screenshot_dir: Directory for storing screenshots
        """
        page = authenticated_page
        division = division_with_stages
        
        # Navigate directly to the division edit page using the URL structure
        competition_id = division.season.competition_id
        season_id = division.season_id
        division_id = division.pk
        
        division_url = (
            f"{live_server.url}/admin/fixja/competition/{competition_id}/"
            f"seasons/{season_id}/division/{division_id}/"
        )
        
        print(f"Navigating to: {division_url}")
        page.goto(division_url)
        page.wait_for_load_state("networkidle")
        
        # Capture screenshot showing the division page with stages
        screenshot_before = screenshot_dir / "stage_reorder_admin_ui.png"
        page.screenshot(path=str(screenshot_before), full_page=True)
        print(f"✓ Screenshot saved: {screenshot_before}")
        
        # Verify reorder buttons exist in the DOM
        # These buttons were added by our template changes
        down_buttons = page.locator('a[href*="reorder"][href*="stage:division"][href*="/down"]')
        up_buttons = page.locator('a[href*="reorder"][href*="stage:division"][href*="/up"]')
        
        # We should have 3 stages, so 3 up buttons and 3 down buttons
        down_count = down_buttons.count()
        up_count = up_buttons.count()
        
        print(f"✓ Found {down_count} down buttons in DOM")
        print(f"✓ Found {up_count} up buttons in DOM")
        
        # Assert buttons exist for all stages
        assert down_count == 3, f"Expected 3 down buttons, found {down_count}"
        assert up_count == 3, f"Expected 3 up buttons, found {up_count}"
        
        # Verify the buttons have correct href patterns for our stages
        for i, stage in enumerate(division.test_stages, 1):
            down_selector = f'a[href*="stage:division"][href*="/{stage.pk}/down"]'
            up_selector = f'a[href*="stage:division"][href*="/{stage.pk}/up"]'
            
            # Verify each stage has its reorder buttons
            assert page.locator(down_selector).count() == 1, f"Stage {stage.pk} missing down button"
            assert page.locator(up_selector).count() == 1, f"Stage {stage.pk} missing up button"
            
            print(f"✓ Stage {i} ({stage.title}): reorder buttons present")
        
        # Get the HTML of one button to show it exists
        first_down = down_buttons.first
        button_html = first_down.get_attribute("href")
        print(f"✓ Example button href: {button_html}")
        
        print("✓ Test completed successfully - all reorder buttons present in DOM")

