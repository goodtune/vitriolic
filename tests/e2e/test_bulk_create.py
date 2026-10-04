"""End-to-end tests for adding several records at once in the admin."""

import pytest
from playwright.sync_api import Page, expect

from tournamentcontrol.competition.tests import factories

#: Note when the next Bootstrap modal has finished fading and sliding in.
WATCH_MODAL_SHOWN = """() => {
    window.bulkCreateModalShown = false;
    $(document).one("shown.bs.modal", () => { window.bulkCreateModalShown = true; });
}"""


def open_modal(page: Page, name: str):
    """
    Open the "how many?" modal for ``name`` and wait until Bootstrap has
    finished showing it, so a screenshot shows it as a person sees it.
    """
    page.evaluate(WATCH_MODAL_SHOWN)
    page.click(f'a[data-target="#bulkCreateModal_{name}"]')
    page.wait_for_function("window.bulkCreateModalShown")
    return page.locator(f"#bulkCreateCount_{name}")


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

        count = open_modal(page, "division")
        expect(count).to_be_visible()
        count.fill("2")
        page.screenshot(path=str(screenshot_dir / "bulk_create_divisions_modal.png"))
        # Enter must open the bulk page, not submit the season form behind it.
        count.press("Enter")

        expect(page).to_have_url(
            f"{live_server.url}{season.urls['edit']}division/bulk/?count=2"
        )
        expect(page.locator("table.bulk-create tbody tr")).to_have_count(2)
        for index, title in enumerate(("Men's Open", "Women's Open")):
            page.fill(f'input[name="form-{index}-title"]', title)
            page.fill(f'input[name="form-{index}-forfeit_for_score"]', "5")
            page.fill(f'input[name="form-{index}-forfeit_against_score"]', "0")
        page.screenshot(
            path=str(screenshot_dir / "bulk_create_divisions_form.png"), full_page=True
        )
        page.click('button[type="submit"]')

        expect(page).to_have_url(
            f"{live_server.url}{season.urls['edit']}#divisions-tab"
        )
        expect(page.locator("#divisions-tab")).to_contain_text("Women's Open")
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

        count = open_modal(page, "team")
        expect(count).to_be_visible()
        count.fill("3")
        page.screenshot(path=str(screenshot_dir / "bulk_create_teams_modal.png"))
        page.click("#bulkCreateModal_team .js-bulk-create")

        expect(page).to_have_url(
            f"{live_server.url}{division.urls['edit']}teams/bulk/?count=3"
        )
        expect(page.locator("table.bulk-create tbody tr")).to_have_count(3)
        page.fill('input[name="form-0-title"]', "Alpha")
        page.fill('input[name="form-2-title"]', "Charlie")
        page.screenshot(
            path=str(screenshot_dir / "bulk_create_teams_form.png"), full_page=True
        )
        page.click('button[type="submit"]')

        expect(page).to_have_url(f"{live_server.url}{division.urls['edit']}#teams-tab")
        expect(page.locator("#teams-tab")).to_contain_text("Charlie")
        page.screenshot(
            path=str(screenshot_dir / "bulk_create_teams_saved.png"), full_page=True
        )
        assert list(division.teams.order_by("order").values_list("title", "order")) == [
            ("Alpha", 1),
            ("Charlie", 2),
        ]
