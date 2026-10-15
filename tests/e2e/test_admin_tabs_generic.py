"""
The tabs of the generic edit view, in both tab modes.

``generic_edit`` gives an edit page a tab per related list: every relation of
the object when the view names none (``related=None``), only the relations it
names, or none at all (``related=()``). Each test runs traditionally (every tab
in the page) and with ``TOUCHTECHNOLOGY_HTMX_ADMIN_TABS`` (each tab fetched
when it is first shown), and expects the same of both.
"""

from urllib.parse import urljoin

import pytest
from django.urls import reverse
from playwright.sync_api import Page, expect

from tests.e2e.admin_tabs import (
    EMPTY_TAB,
    assert_same_in_both_modes,
    read_tabs,
    set_mode,
    show_tab,
)
from tournamentcontrol.competition.models import Season
from tournamentcontrol.competition.tests import factories

MODES = [pytest.param(False, id="plain"), pytest.param(True, id="htmx")]


@pytest.fixture
def competition(db):
    """A competition with two seasons and a role of each kind."""
    competition = factories.CompetitionFactory.create(title="Generic Cup")
    factories.SeasonFactory.create(competition=competition, title="2025")
    factories.SeasonFactory.create(competition=competition, title="2026")
    factories.ClubRoleFactory.create(competition=competition, name="Manager")
    factories.TeamRoleFactory.create(competition=competition, name="Coach")
    return competition


def url(live_server, path):
    return urljoin(live_server.url, str(path))


@pytest.mark.parametrize("htmx", MODES)
def test_a_view_naming_no_relations_has_a_tab_for_each(
    authenticated_page: Page, live_server, settings, competition, htmx
):
    """``edit_competition`` passes no ``related``: every relation gets a tab."""
    set_mode(settings, htmx)
    tabs = read_tabs(
        authenticated_page, url(live_server, competition.urls["edit"])
    )
    assert tabs.errors == []
    assert tabs.ids[0] == "competition-tab"
    assert {"seasons-tab", "club_roles-tab", "team_roles-tab"} <= set(tabs.ids)
    assert {str(season.urls["edit"]) for season in competition.seasons.all()} <= set(
        tabs.links["seasons-tab"]
    )


@pytest.mark.parametrize("htmx", MODES)
def test_a_view_naming_its_relations_has_only_those(
    authenticated_page: Page, live_server, settings, competition, htmx
):
    """``edit_venue`` names ``grounds``: that is its only related tab."""
    set_mode(settings, htmx)
    venue = factories.VenueFactory.create(season=competition.seasons.first())
    grounds = factories.GroundFactory.create_batch(2, venue=venue)
    tabs = read_tabs(authenticated_page, url(live_server, venue.urls["edit"]))
    assert tabs.errors == []
    assert tabs.ids == ["venue-tab", "grounds-tab"]
    assert {str(ground.urls["edit"]) for ground in grounds} <= set(
        tabs.links["grounds-tab"]
    )


@pytest.mark.parametrize("htmx", MODES)
def test_a_view_naming_no_tabs_has_only_the_form(
    authenticated_page: Page, live_server, settings, admin_user, htmx
):
    """``edit_user`` passes ``related=()``: the form is the only tab."""
    set_mode(settings, htmx)
    path = reverse("admin:auth:users:edit", args=[admin_user.pk])
    tabs = read_tabs(authenticated_page, url(live_server, path))
    assert tabs.errors == []
    assert len(tabs.ids) == 1


def test_tabs_list_the_same_in_both_modes(
    authenticated_page: Page, live_server, settings, competition
):
    assert_same_in_both_modes(
        authenticated_page, settings, url(live_server, competition.urls["edit"])
    )


@pytest.mark.parametrize("htmx", MODES)
def test_a_link_in_a_tab_leaves_the_page(
    authenticated_page: Page, live_server, settings, competition, htmx
):
    """Edit on a row of a tab goes to that object's own page."""
    set_mode(settings, htmx)
    page = authenticated_page
    page.goto(url(live_server, competition.urls["edit"]))
    pane = show_tab(page, "seasons-tab")
    row = pane.locator("tbody tr").first
    row.locator("button.dropdown-toggle").click()
    href = row.get_by_role("button", name="Edit").get_attribute("href")
    row.get_by_role("button", name="Edit").click()
    page.wait_for_url(url(live_server, href))
    # The season's page replaced the competition's, rather than being loaded
    # into the tab the link was in.
    expect(page.locator("#myTab")).to_have_count(1)
    expect(page.locator("#season-tab")).to_have_count(1)
    expect(page.locator("#seasons-tab")).to_have_count(0)


@pytest.mark.parametrize("htmx", MODES)
def test_deleting_from_a_tab(
    authenticated_page: Page, live_server, settings, competition, htmx
):
    """Delete on a row of a tab asks first, then deletes that object."""
    set_mode(settings, htmx)
    page = authenticated_page
    season = competition.seasons.get(title="2025")
    page.goto(url(live_server, competition.urls["edit"]))
    pane = show_tab(page, "seasons-tab")
    row = pane.locator("tbody tr", has_text="2025")
    row.locator("button.dropdown-toggle").click()
    row.get_by_role("button", name="Delete").click()

    modal = page.locator("#deleteModal_season")
    expect(modal).to_be_visible()
    expect(modal.locator(".modal-body strong")).to_have_text(str(season))
    # The dialog keeps aria-hidden on it, so find its button by what it is.
    submit = modal.locator("button[type=submit]")
    expect(submit).to_have_text("Delete season")
    submit.click()

    page.wait_for_load_state("networkidle")
    assert not Season.objects.filter(pk=season.pk).exists()
    assert competition.seasons.filter(title="2026").exists()
    expect(page.locator("body")).not_to_contain_text(EMPTY_TAB)


@pytest.mark.parametrize("htmx", MODES)
def test_coming_back_from_an_object_shows_its_tab(
    authenticated_page: Page, live_server, settings, competition, htmx
):
    """Cancel on a season's page returns to the competition's seasons tab."""
    set_mode(settings, htmx)
    page = authenticated_page
    page.goto(url(live_server, competition.urls["edit"]))
    pane = show_tab(page, "seasons-tab")
    row = pane.locator("tbody tr").first
    row.locator("button.dropdown-toggle").click()
    row.get_by_role("button", name="Edit").click()
    expect(page.locator("#season-tab")).to_be_visible()

    page.get_by_role("link", name="Cancel").click()
    page.wait_for_url(url(live_server, competition.urls["edit"]))
    expect(page.locator("#seasons-tab")).to_be_visible()
    expect(page.locator("#seasons-tab tbody tr").first).to_be_visible()


@pytest.mark.parametrize("htmx", MODES)
def test_an_edit_page_opened_directly_has_no_script_errors(
    authenticated_page: Page, live_server, settings, competition, htmx
):
    """
    Opened from a bookmark (no referrer), the page used to fail working out
    which tab to show, which also stopped it setting up its select boxes.
    """
    set_mode(settings, htmx)
    page = authenticated_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url(live_server, competition.urls["edit"]))
    expect(page.locator("#competition-tab")).to_be_visible()
    expect(page.locator(".select2-container").first).to_be_attached()
    assert errors == []
