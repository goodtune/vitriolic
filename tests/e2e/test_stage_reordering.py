"""End-to-end test for Stage reordering functionality in admin interface."""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.shells import ROW_MENU, SHELL, pane_id, tab_link
from tournamentcontrol.competition.tests import factories


class TestStageReordering:
    """Test Stage reordering functionality in the admin UI."""

    @pytest.fixture
    def division_with_stages(self, db):
        """
        Create a division with multiple stages for reordering tests.

        Returns:
            Division: A division with three stages in order
        """
        # Create a complete hierarchy: Competition -> Season -> Division
        division = factories.DivisionFactory.create(title="Under 12")

        # Create three stages in order
        stage1 = factories.StageFactory.create(
            division=division, title="Preliminary", short_title="Prelim", order=1
        )
        stage2 = factories.StageFactory.create(
            division=division, title="Semi-Finals", short_title="Semi", order=2
        )
        stage3 = factories.StageFactory.create(
            division=division, title="Finals", short_title="Final", order=3
        )

        # Store stage IDs for verification
        division.test_stages = [stage1, stage2, stage3]
        return division

    def test_moving_a_stage_down_reorders_the_stages(
        self,
        authenticated_page: Page,
        live_server,
        division_with_stages,
        screenshot_dir,
    ):
        """
        Open the division's Stages tab, open the first stage's actions (where
        the shell keeps them behind a menu) and move it down: the arrow posts,
        the stages are then in a new order in the database, and the browser
        is back on the Stages tab, which lists them that way.
        """
        page = authenticated_page
        division = division_with_stages
        division_url = f"{live_server.url}{division.urls['edit']}"

        page.goto(division_url)
        page.locator(tab_link("stages")).click()
        pane = page.locator(f"#{pane_id('stages')}")
        expect(pane).to_be_visible()
        rows = pane.locator("tbody tr")
        expect(rows).to_have_count(3)
        expect(rows.first).to_contain_text("Preliminary")
        page.screenshot(
            path=str(screenshot_dir / "stage_reorder_before.png"), full_page=True
        )

        first = rows.first
        if SHELL == "workbook":
            first.get_by_role("button", name=ROW_MENU).click()
        first.get_by_role("button", name=re.compile(r"Move.*down")).click()
        expect(page).to_have_url(f"{division_url}#stages-tab")
        page.wait_for_load_state("networkidle")

        titles = list(division.stages.order_by("order").values_list("title", flat=True))
        assert titles == ["Semi-Finals", "Preliminary", "Finals"], titles

        rows = page.locator(f"#{pane_id('stages')} tbody tr")
        expect(rows.first).to_contain_text("Semi-Finals")
        expect(rows.nth(1)).to_contain_text("Preliminary")
        page.screenshot(
            path=str(screenshot_dir / "stage_reorder_after_move_down.png"),
            full_page=True,
        )
