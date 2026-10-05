"""End-to-end tests for HTMX admin tabs.

Tests both the traditional (legacy) tab mode and the HTMX-driven tabs, which
load each related tab when it is first shown and list its objects a page at a
time, ensuring functionality across both modes. Screenshots of each step are
saved to ``screenshot_dir`` and posted on the pull request.
"""

from urllib.parse import urljoin

import pytest
from django.urls import reverse
from playwright.sync_api import Page, expect

from tournamentcontrol.competition.tests import factories


def shoot(page: Page, screenshot_dir, name: str):
    """Save a full page screenshot as ``<name>.png``."""
    page.screenshot(path=str(screenshot_dir / f"{name}.png"), full_page=True)


@pytest.fixture
def competition_data(db):
    """Create test competition data for tab testing."""
    competition = factories.CompetitionFactory.create()
    season = factories.SeasonFactory.create(competition=competition)
    division = factories.DivisionFactory.create(season=season)
    venue = factories.VenueFactory.create(season=season)
    return {
        "competition": competition,
        "season": season,
        "division": division,
        "venue": venue,
    }


@pytest.fixture
def club_data(db):
    """
    A club with more people and teams than fit on one page of a tab, and a
    person at another club who must not be offered as its primary contact.
    """
    club = factories.ClubFactory.create()
    members = [
        club.members.create(first_name="Alice", last_name=f"Member{n:02d}")
        for n in range(1, 26)
    ]
    division = factories.DivisionFactory.create()
    division.season.competition.clubs.add(club)
    teams = factories.TeamFactory.create_batch(12, club=club, division=division)
    outsider = factories.PersonFactory.create(first_name="Olivia", last_name="Outsider")
    return {
        "club": club,
        "members": members,
        "teams": teams,
        "outsider": outsider,
    }


def competition_edit_url(live_server, competition):
    path = reverse("admin:fixja:competition:edit", args=[competition.pk])
    return urljoin(live_server.url, path)


def season_edit_url(live_server, competition, season):
    path = reverse(
        "admin:fixja:competition:season:edit",
        args=[competition.pk, season.pk],
    )
    return urljoin(live_server.url, path)


def club_edit_url(live_server, club):
    path = reverse("admin:fixja:club:edit", args=[club.pk])
    return urljoin(live_server.url, path)


class TestTraditionalTabMode:
    """Tests for the traditional (non-HTMX) tab-based admin interface."""

    def test_competition_edit_shows_tabs(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """Competition edit page shows tab navigation in traditional mode."""
        competition = competition_data["competition"]
        authenticated_page.goto(competition_edit_url(live_server, competition))

        # Verify tab navigation sidebar is present
        tab_nav = authenticated_page.locator("#myTab")
        expect(tab_nav).to_be_visible()

        # Verify the Edit tab link exists with data-toggle="tab"
        edit_tab = authenticated_page.locator('#myTab a[data-toggle="tab"]').first
        expect(edit_tab).to_be_visible()
        shoot(authenticated_page, screenshot_dir, "tabs_traditional_competition_edit")

    def test_competition_edit_form_present(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """Competition edit page has a working form with Save button."""
        competition = competition_data["competition"]
        authenticated_page.goto(competition_edit_url(live_server, competition))

        # Verify the form is present
        form = authenticated_page.locator("form.form-horizontal")
        expect(form).to_be_visible()

        # Verify Save button exists
        save_button = authenticated_page.locator(
            '.tab-pane.active button[type="submit"]'
        )
        expect(save_button).to_be_visible()
        expect(save_button).to_have_text("Save")

    def test_season_edit_shows_related_tabs(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """Season edit page shows related object tabs."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(season_edit_url(live_server, competition, season))

        # Verify tab navigation exists
        tab_nav = authenticated_page.locator("#myTab")
        expect(tab_nav).to_be_visible()

        # There should be multiple tabs (edit + related objects)
        tab_links = authenticated_page.locator('#myTab a[data-toggle="tab"]')
        expect(tab_links.first).to_be_visible()
        assert tab_links.count() > 1
        shoot(authenticated_page, screenshot_dir, "tabs_traditional_season_edit")

    def test_season_tab_switching(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """Clicking tab links in traditional mode switches visible content."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(season_edit_url(live_server, competition, season))

        # Get the first related tab link (not the main edit tab)
        related_tabs = authenticated_page.locator(
            '#myTab li:not(.active) a[data-toggle="tab"]'
        )
        assert related_tabs.count() > 0

        # Click the first related tab
        first_tab = related_tabs.first
        tab_href = first_tab.get_attribute("href")
        first_tab.click()

        # Verify the related tab pane becomes active
        tab_pane = authenticated_page.locator(f"#{tab_href.lstrip('#')}")
        expect(tab_pane).to_be_visible()
        shoot(
            authenticated_page, screenshot_dir, "tabs_traditional_season_tab_switched"
        )

    def test_competition_form_submit_redirects(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """Saving the primary form redirects to the upper-level page."""
        competition = competition_data["competition"]
        edit_url = competition_edit_url(live_server, competition)
        authenticated_page.goto(edit_url)

        # Click Save without changing anything
        save_button = authenticated_page.locator(
            '.tab-pane.active button[type="submit"]'
        )
        save_button.click()

        # Wait for redirect - should go back to competition list
        authenticated_page.wait_for_load_state("networkidle")

        # Should not stay on the edit page (redirected to parent)
        current_url = authenticated_page.url
        assert edit_url not in current_url or ("?r=" in current_url)
        shoot(authenticated_page, screenshot_dir, "tabs_traditional_competition_saved")

    def test_no_htmx_attributes_in_traditional_mode(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """Traditional mode should not have HTMX attributes on elements."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(season_edit_url(live_server, competition, season))

        # Check that no hx-get attributes exist on tab links
        htmx_links = authenticated_page.locator("[hx-get]")
        assert htmx_links.count() == 0

        # Check that no hx-trigger attributes exist
        htmx_triggers = authenticated_page.locator("[hx-trigger]")
        assert htmx_triggers.count() == 0

    def test_club_edit_lists_every_person_up_front(
        self, authenticated_page: Page, live_server, club_data, screenshot_dir
    ):
        """Without HTMX the people tab is rendered with the page, in full."""
        url = club_edit_url(live_server, club_data["club"])
        html = authenticated_page.request.get(url).text()
        assert html.count(", Alice</a>") == len(club_data["members"])
        authenticated_page.goto(url)
        authenticated_page.locator('a[href="#members-tab"]').click()
        expect(authenticated_page.locator("#members-tab")).to_be_visible()
        shoot(authenticated_page, screenshot_dir, "tabs_traditional_club_people")


class TestHtmxTabMode:
    """Tests for the HTMX-driven admin interface."""

    @pytest.fixture(autouse=True)
    def enable_htmx_tabs(self, settings):
        """Enable HTMX admin tabs for all tests in this class."""
        settings.TOUCHTECHNOLOGY_HTMX_ADMIN_TABS = True

    def test_htmx_script_loaded(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """HTMX script is loaded when the feature flag is enabled."""
        competition = competition_data["competition"]
        authenticated_page.goto(competition_edit_url(live_server, competition))

        # Check that the htmx script is present, and that it was served: the
        # library defines a global when it has run.
        htmx_script = authenticated_page.locator('script[src*="htmx"]')
        expect(htmx_script).to_have_count(1)
        assert authenticated_page.evaluate("typeof htmx") == "object"
        shoot(authenticated_page, screenshot_dir, "tabs_htmx_competition_edit")

    def test_season_edit_has_htmx_attributes(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """Season edit page has HTMX attributes on the related tab panes."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(season_edit_url(live_server, competition, season))

        # Related tab panes should have hx-get attributes
        htmx_panes = authenticated_page.locator(".tab-pane[hx-get]")
        assert htmx_panes.count() > 0

    def test_season_edit_lazy_load_attributes(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """Related tab panes load when first shown, not with the page."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(season_edit_url(live_server, competition, season))

        # Tab panes should have hx-trigger="intersect once"
        lazy_panes = authenticated_page.locator(
            '.tab-pane[hx-trigger="intersect once"]'
        )
        assert lazy_panes.count() > 0

    def test_season_edit_form_inside_tab(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """In HTMX mode, the form is inside the tab pane, not wrapping all."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(season_edit_url(live_server, competition, season))

        # In HTMX mode, form should be inside the active tab pane
        tab_pane_form = authenticated_page.locator(
            ".tab-pane.active form.form-horizontal"
        )
        expect(tab_pane_form).to_be_visible()
        shoot(authenticated_page, screenshot_dir, "tabs_htmx_season_edit")

    def test_season_edit_primary_form_save(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """Saving primary form in HTMX mode redirects to parent page."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        url = season_edit_url(live_server, competition, season)
        authenticated_page.goto(url)

        # Click Save
        save_button = authenticated_page.locator(
            '.tab-pane.active button[type="submit"]'
        )
        expect(save_button).to_be_visible()
        save_button.click()

        # Should redirect (primary form save goes to parent)
        authenticated_page.wait_for_load_state("networkidle")
        current_url = authenticated_page.url
        # Should redirect to competition edit page
        season_path = reverse(
            "admin:fixja:competition:season:edit",
            args=[competition.pk, season.pk],
        )
        assert season_path not in current_url
        shoot(authenticated_page, screenshot_dir, "tabs_htmx_season_saved")

    def test_htmx_tab_content_loads_dynamically(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """Related tab content loads dynamically via HTMX."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(season_edit_url(live_server, competition, season))

        # Wait for HTMX to be ready
        authenticated_page.wait_for_load_state("networkidle")

        # Nothing is fetched until a tab is shown, so every related pane is
        # still waiting behind its spinner.
        related_panes = authenticated_page.locator(".tab-pane[hx-get]")
        assert related_panes.count() > 0
        first_pane = related_panes.first
        expect(first_pane.locator(".fa-spinner")).to_have_count(1)

        # Showing the tab loads its content in place of the spinner.
        tab_id = first_pane.get_attribute("id")
        authenticated_page.locator(f'a[href="#{tab_id}"]').click()
        expect(first_pane).to_be_visible()
        expect(first_pane.locator(".fa-spinner")).to_have_count(0)
        shoot(authenticated_page, screenshot_dir, "tabs_htmx_season_tab_loaded")

    def test_competition_edit_page_loads(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """Competition edit page loads correctly in HTMX mode."""
        competition = competition_data["competition"]
        authenticated_page.goto(competition_edit_url(live_server, competition))

        # Page should load without errors
        tab_nav = authenticated_page.locator("#myTab")
        expect(tab_nav).to_be_visible()

        # Edit tab should be active
        active_tab = authenticated_page.locator("#myTab li.active")
        expect(active_tab).to_be_visible()

    def test_tab_click_shows_content(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """Clicking an HTMX tab link shows the tab content."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(season_edit_url(live_server, competition, season))

        # Wait for page to be fully loaded
        authenticated_page.wait_for_load_state("networkidle")

        # Find a related tab link and click it
        htmx_tabs = authenticated_page.locator("#myTab li:not(.active) a.htmx-tab-link")
        assert htmx_tabs.count() > 0

        first_htmx_tab = htmx_tabs.first
        tab_id = first_htmx_tab.get_attribute("data-tab-id")
        first_htmx_tab.click()

        # The target tab pane should now be visible, with its content loaded
        # in place of the spinner.
        target_pane = authenticated_page.locator(f"#{tab_id}")
        expect(target_pane).to_be_visible()
        expect(target_pane.locator(".fa-spinner")).to_have_count(0)
        shoot(authenticated_page, screenshot_dir, "tabs_htmx_season_tab_clicked")

    def test_tab_is_fetched_once(
        self, authenticated_page: Page, live_server, competition_data, screenshot_dir
    ):
        """Showing a tab again does not fetch it again."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        fetched = []
        authenticated_page.on(
            "request",
            lambda request: (
                fetched.append(request.url) if "_htmx_tab=" in request.url else None
            ),
        )
        authenticated_page.goto(season_edit_url(live_server, competition, season))
        authenticated_page.wait_for_load_state("networkidle")
        assert fetched == []

        links = authenticated_page.locator("#myTab li:not(.active) a.htmx-tab-link")
        tab_id = links.first.get_attribute("data-tab-id")
        pane = authenticated_page.locator(f"#{tab_id}")
        for _ in range(2):
            links.first.click()
            expect(pane).to_be_visible()
            authenticated_page.locator("#myTab li:first-child a.htmx-tab-link").click()
            expect(pane).to_be_hidden()
        authenticated_page.wait_for_load_state("networkidle")
        assert len(fetched) == 1


class TestHtmxTabPagination:
    """Related tabs list one page of their objects at a time."""

    @pytest.fixture(autouse=True)
    def enable_htmx_tabs(self, settings):
        """Enable HTMX admin tabs, ten objects to a page."""
        settings.TOUCHTECHNOLOGY_HTMX_ADMIN_TABS = True
        settings.TOUCHTECHNOLOGY_HTMX_ADMIN_TAB_PAGINATE_BY = 10

    def test_tabs_wait_until_shown(
        self, authenticated_page: Page, live_server, club_data, screenshot_dir
    ):
        """Opening a club fetches none of its tabs until one is shown."""
        fetched = []
        authenticated_page.on(
            "request",
            lambda request: (
                fetched.append(request.url) if "_htmx_tab=" in request.url else None
            ),
        )
        authenticated_page.goto(club_edit_url(live_server, club_data["club"]))
        authenticated_page.wait_for_load_state("networkidle")

        assert fetched == []
        expect(
            authenticated_page.locator(".tab-pane[hx-get] .fa-spinner")
        ).to_have_count(2)
        shoot(authenticated_page, screenshot_dir, "club_tabs_waiting")

        authenticated_page.locator('a[href="#members-tab"]').click()
        expect(authenticated_page.locator("#members-tab tbody tr")).to_have_count(10)
        authenticated_page.wait_for_load_state("networkidle")
        assert len(fetched) == 1
        assert "_htmx_tab=members" in fetched[0]
        # The teams tab is still waiting to be shown.
        expect(authenticated_page.locator("#teams-tab .fa-spinner")).to_have_count(1)

    def test_people_tab_pages(
        self, authenticated_page: Page, live_server, club_data, screenshot_dir
    ):
        """The people tab lists ten people, and each page link shows more."""
        page = authenticated_page
        url = club_edit_url(live_server, club_data["club"])
        page.goto(url)
        history_length = page.evaluate("history.length")

        page.locator('a[href="#members-tab"]').click()
        rows = page.locator("#members-tab tbody tr")
        expect(rows).to_have_count(10)
        expect(rows.first).to_contain_text("Member01")
        expect(rows.last).to_contain_text("Member10")
        expect(page.locator("#members-tab ul.pagination li.current")).to_have_text("1")
        shoot(page, screenshot_dir, "club_people_page_1")

        page.locator('#members-tab ul.pagination a[href$="page=2"]').click()
        expect(rows.first).to_contain_text("Member11")
        expect(rows.last).to_contain_text("Member20")
        expect(page.locator("#members-tab ul.pagination li.current")).to_have_text("2")
        shoot(page, screenshot_dir, "club_people_page_2")

        page.locator('#members-tab ul.pagination a[href$="page=3"]').click()
        expect(rows).to_have_count(5)
        expect(rows.first).to_contain_text("Member21")
        expect(rows.last).to_contain_text("Member25")
        expect(page.locator("#members-tab ul.pagination li.current")).to_have_text("3")
        shoot(page, screenshot_dir, "club_people_page_3")

        # The tab changed in place: the address and the history did not.
        assert page.url == url
        assert page.evaluate("history.length") == history_length
        expect(page.locator("#myTab")).to_be_visible()

    def test_teams_tab_pages(
        self, authenticated_page: Page, live_server, club_data, screenshot_dir
    ):
        """Teams, which are a queryset rather than a list, are paged too."""
        page = authenticated_page
        page.goto(club_edit_url(live_server, club_data["club"]))

        page.locator('a[href="#teams-tab"]').click()
        rows = page.locator("#teams-tab tbody tr")
        expect(rows).to_have_count(10)
        shoot(page, screenshot_dir, "club_teams_page_1")

        page.locator('#teams-tab ul.pagination a[href$="page=2"]').click()
        expect(rows).to_have_count(2)
        expect(page.locator("#teams-tab ul.pagination li.current")).to_have_text("2")
        shoot(page, screenshot_dir, "club_teams_page_2")

    def test_pages_are_independent_between_tabs(
        self, authenticated_page: Page, live_server, club_data, screenshot_dir
    ):
        """Turning the page of one tab leaves the other where it was."""
        page = authenticated_page
        page.goto(club_edit_url(live_server, club_data["club"]))

        page.locator('a[href="#teams-tab"]').click()
        expect(page.locator("#teams-tab tbody tr")).to_have_count(10)
        page.locator('a[href="#members-tab"]').click()
        expect(page.locator("#members-tab tbody tr")).to_have_count(10)
        page.locator('#members-tab ul.pagination a[href$="page=2"]').click()
        expect(page.locator("#members-tab tbody tr").first).to_contain_text("Member11")

        page.locator('a[href="#teams-tab"]').click()
        expect(page.locator("#teams-tab ul.pagination li.current")).to_have_text("1")
        shoot(page, screenshot_dir, "club_tabs_independent_pages")

    def test_primary_contact_offers_only_the_clubs_people(
        self, authenticated_page: Page, live_server, club_data, screenshot_dir
    ):
        """The primary contact is chosen from the club's own people."""
        page = authenticated_page
        page.goto(club_edit_url(live_server, club_data["club"]))

        options = page.locator('select[name="primary"] option')
        # Every member, and the blank choice.
        expect(options).to_have_count(len(club_data["members"]) + 1)
        expect(
            page.locator('select[name="primary"] option', has_text="Outsider")
        ).to_have_count(0)
        shoot(page, screenshot_dir, "club_edit_primary_contact")

    def test_club_form_saves_with_a_primary_contact(
        self, authenticated_page: Page, live_server, club_data, screenshot_dir
    ):
        """The club form still saves, with one of its people as the contact."""
        page = authenticated_page
        club = club_data["club"]
        member = club_data["members"][0]
        page.goto(club_edit_url(live_server, club))

        # Select2 hides the select it replaces.
        page.select_option('select[name="primary"]', str(member.pk), force=True)
        page.locator('.tab-pane.active button[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        club.refresh_from_db()
        assert club.primary_id == member.pk
        shoot(page, screenshot_dir, "club_edit_saved")
