"""
End-to-end validation of Workbook's set-up checklist on the season and
division pages: the fold the person chooses is remembered across page loads,
the checklists can be hidden and brought back (also remembered), a finished
checklist starts folded, a folded checklist is never drawn open first, and
all of it works from the keyboard.

Prerequisites: the Workbook shell (Explorer shows the steps in a Set-up tab
instead, with nothing to fold or hide). The browser's localStorage holds the
choices: ``wb-checklist-fold:<kind>`` ("open" or "folded") and
``wb-checklists`` ("hidden").
"""

import datetime

import pytest
from django.urls import reverse
from playwright.sync_api import Page, expect

from tests.e2e.shells import SHELL
from tournamentcontrol.competition.tests import factories

pytestmark = pytest.mark.skipif(
    SHELL != "workbook", reason="Explorer's set-up checklist is a tab, not a panel"
)

DESK = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}

#: Records, before every frame is drawn and at DOMContentLoaded, whether the
#: season checklist's steps could be seen.
WATCH = """
window.__checklist = {frames: [], loaded: null};
function look() {
    var details = document.querySelector("details[data-wb-checklist]");
    var steps = details && details.querySelector(".wb-steps");
    return steps ? {
        open: details.open,
        shown: getComputedStyle(steps).display !== "none" && details.open,
    } : null;
}
(function frame() {
    var seen = look();
    if (seen) { window.__checklist.frames.push(seen); }
    if (document.readyState !== "complete") { requestAnimationFrame(frame); }
})();
document.addEventListener("DOMContentLoaded", function () {
    window.__checklist.loaded = look();
});
"""


def season_url(season):
    return reverse(
        "admin:fixja:competition:season:edit", args=(season.competition_id, season.pk)
    )


def division_url(division):
    return reverse(
        "admin:fixja:competition:season:division:edit",
        args=(division.season.competition_id, division.season_id, division.pk),
    )


@pytest.fixture
def unfinished(db):
    """A season with a division and nothing else: most steps still to do."""
    season = factories.SeasonFactory.create(
        title="Spring 2026", start_date=datetime.date(2026, 9, 16)
    )
    factories.DivisionFactory.create(season=season, title="Mixed Open")
    return season


@pytest.fixture
def finished(db):
    """A season with every required step done (no dates set aside)."""
    season = factories.SeasonFactory.create(
        title="Autumn 2026", start_date=datetime.date(2026, 3, 4)
    )
    factories.SeasonMatchTimeFactory.create(season=season)
    ground = factories.GroundFactory.create(venue__season=season)
    division = factories.DivisionFactory.create(season=season, title="Mixed Open")
    home, away = factories.TeamFactory.create_batch(2, division=division)
    kick_off = datetime.datetime(2026, 3, 4, 18, 0, tzinfo=datetime.UTC)
    factories.MatchFactory.create(
        stage=factories.StageFactory.create(division=division),
        home_team=home,
        away_team=away,
        play_at=ground,
        datetime=kick_off,
        date=kick_off.date(),
        time=kick_off.time(),
    )
    return season


def checklist(page):
    return page.locator("details[data-wb-checklist]")


def steps(page):
    return checklist(page).locator(".wb-steps")


def stored(page, key):
    return page.evaluate("key => localStorage.getItem(key)", key)


def test_the_fold_is_remembered(
    authenticated_page: Page, live_server, unfinished, screenshot_dir
):
    """
    An unfinished checklist starts open at a desk. Folding it is kept for the
    next page load, and so is opening it again.
    """
    page = authenticated_page
    page.set_viewport_size(DESK)
    page.goto(live_server.url + season_url(unfinished))
    expect(steps(page)).to_be_visible()

    checklist(page).locator("summary").click()
    expect(steps(page)).to_be_hidden()
    assert stored(page, "wb-checklist-fold:season") == "folded"

    page.reload()
    expect(checklist(page)).to_have_attribute("data-wb-ready", "")
    expect(steps(page)).to_be_hidden()
    page.screenshot(path=screenshot_dir / "setup_checklist_folded.png")

    checklist(page).locator("summary").click()
    expect(steps(page)).to_be_visible()
    page.reload()
    expect(steps(page)).to_be_visible()
    assert stored(page, "wb-checklist-fold:season") == "open"


def test_a_finished_checklist_starts_folded(
    authenticated_page: Page, live_server, finished, unfinished
):
    """
    With no choice stored, a checklist whose required steps are all done
    starts folded and an unfinished one starts open. A choice to open the
    finished one is kept.
    """
    page = authenticated_page
    page.set_viewport_size(DESK)
    page.goto(live_server.url + season_url(finished))
    expect(checklist(page).locator(".wb-checklist-score")).to_have_text("All done")
    expect(steps(page)).to_be_hidden()
    assert stored(page, "wb-checklist-fold:season") is None

    page.goto(live_server.url + season_url(unfinished))
    expect(steps(page)).to_be_visible()

    page.goto(live_server.url + season_url(finished))
    checklist(page).locator("summary").click()
    page.reload()
    expect(steps(page)).to_be_visible()


def test_a_folded_checklist_is_never_drawn_open(
    authenticated_page: Page, live_server, unfinished
):
    """
    The server draws the unfinished checklist open; with "folded" stored the
    page must fold it before it is drawn: at DOMContentLoaded and in every
    frame up to the load, its steps are out of sight.
    """
    page = authenticated_page
    page.set_viewport_size(DESK)
    page.evaluate("localStorage.setItem('wb-checklist-fold:season', 'folded')")
    page.add_init_script(WATCH)
    page.goto(live_server.url + season_url(unfinished))
    page.wait_for_load_state("load")
    seen = page.evaluate("window.__checklist")
    assert seen["loaded"] == {"open": False, "shown": False}
    assert [frame for frame in seen["frames"] if frame["shown"]] == []
    expect(steps(page)).to_be_hidden()


def test_hiding_and_bringing_back(
    authenticated_page: Page, live_server, unfinished, screenshot_dir
):
    """
    Hide puts the set-up checklists of both kinds away until the page head's
    "Show set-up checklist" brings them back; both choices outlast a reload,
    at a desk and on a phone.
    """
    page = authenticated_page
    division = unfinished.divisions.get()
    for size in (DESK, PHONE):
        page.set_viewport_size(size)
        page.goto(live_server.url + season_url(unfinished))
        show = page.get_by_role("button", name="Show set-up checklist")
        expect(show).to_be_hidden()

        page.get_by_role("button", name="Hide the set-up checklists").click()
        expect(checklist(page)).to_be_hidden()
        expect(show).to_be_visible()
        expect(show).to_be_in_viewport()
        assert stored(page, "wb-checklists") == "hidden"

        page.reload()
        expect(checklist(page)).to_be_hidden()
        expect(show).to_be_in_viewport()
        page.screenshot(
            path=screenshot_dir / f"setup_checklist_hidden_{size['width']}.png"
        )

        # One switch for every kind of set-up checklist.
        page.goto(live_server.url + division_url(division))
        expect(checklist(page)).to_be_hidden()
        page.get_by_role("button", name="Show set-up checklist").click()
        expect(checklist(page)).to_be_visible()
        assert stored(page, "wb-checklists") is None

        page.goto(live_server.url + season_url(unfinished))
        expect(checklist(page)).to_be_visible()
        expect(show).to_be_hidden()


def test_the_checklist_works_from_the_keyboard(
    authenticated_page: Page, live_server, unfinished
):
    """
    The summary folds and opens with Enter and Space and shows where the focus
    is; Hide and Show are buttons, and each hands the focus to the other
    control so it is not lost.
    """
    page = authenticated_page
    page.set_viewport_size(DESK)
    page.goto(live_server.url + season_url(unfinished))
    hide = page.get_by_role("button", name="Hide the set-up checklists")
    summary = checklist(page).locator("summary")

    hide.focus()
    page.keyboard.press("Tab")
    expect(summary).to_be_focused()
    assert summary.evaluate("el => getComputedStyle(el).outlineStyle") == "solid"
    page.keyboard.press("Enter")
    expect(steps(page)).to_be_hidden()
    assert stored(page, "wb-checklist-fold:season") == "folded"
    page.keyboard.press("Space")
    expect(steps(page)).to_be_visible()
    assert stored(page, "wb-checklist-fold:season") == "open"

    hide.focus()
    page.keyboard.press("Enter")
    show = page.get_by_role("button", name="Show set-up checklist")
    expect(show).to_be_focused()
    page.keyboard.press("Enter")
    expect(summary).to_be_focused()
    expect(steps(page)).to_be_visible()
