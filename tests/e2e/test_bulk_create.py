"""End-to-end tests for adding several records at once in the admin."""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.shells import BULK_ROWS, by_shell, pane_id
from tournamentcontrol.competition.tests import factories


def open_modal(page: Page, title: str):
    """
    Open the "how many?" dialog that the button called ``title`` opens, and
    return its box for the number.
    """
    # Workbook opens it from a button, Explorer from a link of the list.
    page.get_by_role(by_shell(workbook="button", explorer="link"), name=title).click()
    dialog = page.get_by_role("dialog", name=title)
    expect(dialog).to_be_visible()
    return dialog.get_by_label(
        by_shell(workbook="How many do you want to add?", explorer="How many?")
    )


class TestBulkCreate:
    """Ask how many, fill in the rows, save them all."""

    @pytest.fixture
    def season(self, db):
        season = factories.SeasonFactory.create(title="2027")
        factories.DivisionFactory.create(season=season, title="Mixed", order=1)
        return season

    def test_bulk_create_divisions(
        self, authenticated_page: Page, live_server, season, screenshot_dir
    ):
        page = authenticated_page
        page.goto(f"{live_server.url}{season.urls['edit']}#divisions-tab")

        count = open_modal(page, "Add several divisions")
        expect(count).to_be_visible()
        count.fill("2")
        page.screenshot(path=str(screenshot_dir / "bulk_create_divisions_modal.png"))
        # Enter must open the bulk page, not submit the season form behind it.
        count.press("Enter")

        expect(page).to_have_url(
            f"{live_server.url}{season.urls['edit']}division/bulk/?count=2"
        )
        expect(page.locator(BULK_ROWS)).to_have_count(2)
        for index, title in enumerate(("Men's Open", "Women's Open")):
            page.fill(f'input[name="form-{index}-title"]', title)
            page.fill(f'input[name="form-{index}-forfeit_for_score"]', "5")
            page.fill(f'input[name="form-{index}-forfeit_against_score"]', "0")
        page.screenshot(
            path=str(screenshot_dir / "bulk_create_divisions_form.png"), full_page=True
        )
        page.get_by_role("button", name="Save", exact=True).first.click()

        expect(page).to_have_url(
            f"{live_server.url}{season.urls['edit']}#divisions-tab"
        )
        expect(page.locator(f"#{pane_id('divisions')}")).to_contain_text("Women's Open")
        page.screenshot(
            path=str(screenshot_dir / "bulk_create_divisions_saved.png"), full_page=True
        )
        assert list(
            season.divisions.order_by("order").values_list("title", "order")
        ) == [("Mixed", 1), ("Men's Open", 2), ("Women's Open", 3)]

    def test_bulk_create_teams(
        self, authenticated_page: Page, live_server, season, screenshot_dir
    ):
        division = season.divisions.get()
        page = authenticated_page
        page.goto(f"{live_server.url}{division.urls['edit']}#teams-tab")

        count = open_modal(page, "Add several teams")
        expect(count).to_be_visible()
        count.fill("3")
        page.screenshot(path=str(screenshot_dir / "bulk_create_teams_modal.png"))
        page.get_by_role("dialog", name="Add several teams").get_by_role(
            "button", name="Continue"
        ).click()

        expect(page).to_have_url(
            f"{live_server.url}{division.urls['edit']}teams/bulk/?count=3"
        )
        expect(page.locator(BULK_ROWS)).to_have_count(3)
        page.fill('input[name="form-0-title"]', "Alpha")
        page.fill('input[name="form-2-title"]', "Charlie")
        page.screenshot(
            path=str(screenshot_dir / "bulk_create_teams_form.png"), full_page=True
        )
        page.get_by_role("button", name="Save", exact=True).first.click()

        expect(page).to_have_url(f"{live_server.url}{division.urls['edit']}#teams-tab")
        expect(page.locator(f"#{pane_id('teams')}")).to_contain_text("Charlie")
        page.screenshot(
            path=str(screenshot_dir / "bulk_create_teams_saved.png"), full_page=True
        )
        assert list(division.teams.order_by("order").values_list("title", "order")) == [
            ("Alpha", 1),
            ("Charlie", 2),
        ]
