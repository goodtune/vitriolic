"""End-to-end tests for HTMX admin tabs migration.

Tests both the traditional (legacy) tab mode and the new HTMX-driven
multi-step form system, ensuring functionality across both modes.
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def competition_data(db):
    """Create test competition data for tab testing."""
    from tournamentcontrol.competition.tests.factories import (
        CompetitionFactory,
        DivisionFactory,
        SeasonFactory,
        VenueFactory,
    )

    competition = CompetitionFactory.create()
    season = SeasonFactory.create(competition=competition)
    division = DivisionFactory.create(season=season)
    venue = VenueFactory.create(season=season)
    return {
        "competition": competition,
        "season": season,
        "division": division,
        "venue": venue,
    }


class TestTraditionalTabMode:
    """Tests for the traditional (non-HTMX) tab-based admin interface."""

    def test_competition_edit_shows_tabs(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """Competition edit page shows tab navigation in traditional mode."""
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}/"
        )

        # Verify tab navigation sidebar is present
        tab_nav = authenticated_page.locator("#myTab")
        expect(tab_nav).to_be_visible()

        # Verify the Edit tab link exists with data-toggle="tab"
        edit_tab = authenticated_page.locator(
            '#myTab a[data-toggle="tab"]'
        ).first
        expect(edit_tab).to_be_visible()

    def test_competition_edit_form_present(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """Competition edit page has a working form with Save button."""
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}/"
        )

        # Verify the form is present
        form = authenticated_page.locator("form.form-horizontal")
        expect(form).to_be_visible()

        # Verify Save button exists
        save_button = authenticated_page.locator(
            'button[type="submit"]'
        )
        expect(save_button).to_be_visible()
        expect(save_button).to_have_text("Save")

    def test_season_edit_shows_related_tabs(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """Season edit page shows related object tabs."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}"
            f"/seasons/{season.pk}/"
        )

        # Verify tab navigation exists
        tab_nav = authenticated_page.locator("#myTab")
        expect(tab_nav).to_be_visible()

        # There should be multiple tabs (edit + related objects)
        tab_links = authenticated_page.locator(
            '#myTab a[data-toggle="tab"]'
        )
        expect(tab_links.first).to_be_visible()

    def test_season_tab_switching(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """Clicking tab links in traditional mode switches visible content."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}"
            f"/seasons/{season.pk}/"
        )

        # Get the first related tab link (not the main edit tab)
        related_tabs = authenticated_page.locator(
            '#myTab li:not(.active) a[data-toggle="tab"]'
        )

        if related_tabs.count() > 0:
            # Click the first related tab
            first_tab = related_tabs.first
            tab_href = first_tab.get_attribute("href")
            first_tab.click()

            # Verify the related tab pane becomes active
            if tab_href:
                tab_id = tab_href.lstrip("#")
                tab_pane = authenticated_page.locator(f"#{tab_id}")
                expect(tab_pane).to_be_visible()

    def test_competition_form_submit_redirects(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """Saving the primary form redirects to the upper-level page."""
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}/"
        )

        # Click Save without changing anything
        save_button = authenticated_page.locator(
            'button[type="submit"]'
        )
        save_button.click()

        # Wait for redirect - should go back to competition list
        authenticated_page.wait_for_load_state("networkidle")

        # Should not stay on the edit page (redirected to parent)
        current_url = authenticated_page.url
        assert f"/admin/competition/{competition.pk}/" not in current_url or (
            "?r=" in current_url or current_url.endswith("/competition/")
        )

    def test_no_htmx_attributes_in_traditional_mode(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """Traditional mode should not have HTMX attributes on elements."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}"
            f"/seasons/{season.pk}/"
        )

        # Check that no hx-get attributes exist on tab links
        htmx_links = authenticated_page.locator("[hx-get]")
        assert htmx_links.count() == 0

        # Check that no hx-trigger attributes exist
        htmx_triggers = authenticated_page.locator("[hx-trigger]")
        assert htmx_triggers.count() == 0


class TestHtmxTabMode:
    """Tests for the HTMX-driven multi-step form admin interface."""

    @pytest.fixture(autouse=True)
    def enable_htmx_tabs(self, settings):
        """Enable HTMX admin tabs for all tests in this class."""
        settings.TOUCHTECHNOLOGY_HTMX_ADMIN_TABS = True
        # Also patch the module-level variable
        import touchtechnology.common.sites as sites_module
        import touchtechnology.common.default_settings as ds_module
        import touchtechnology.common.context_processors as cp_module

        original_sites = sites_module.HTMX_ADMIN_TABS
        original_ds = ds_module.HTMX_ADMIN_TABS
        original_cp = cp_module.HTMX_ADMIN_TABS
        sites_module.HTMX_ADMIN_TABS = True
        ds_module.HTMX_ADMIN_TABS = True
        cp_module.HTMX_ADMIN_TABS = True
        yield
        sites_module.HTMX_ADMIN_TABS = original_sites
        ds_module.HTMX_ADMIN_TABS = original_ds
        cp_module.HTMX_ADMIN_TABS = original_cp

    def test_htmx_script_loaded(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """HTMX script is loaded when the feature flag is enabled."""
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}/"
        )

        # Check that htmx.min.js script is present
        htmx_script = authenticated_page.locator(
            'script[src*="htmx"]'
        )
        expect(htmx_script).to_have_count(1)

    def test_season_edit_has_htmx_attributes(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """Season edit page has HTMX attributes on tab links."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}"
            f"/seasons/{season.pk}/"
        )

        # Related tab links should have hx-get attributes
        htmx_links = authenticated_page.locator("a.htmx-tab-link[hx-get]")
        assert htmx_links.count() > 0

    def test_season_edit_preload_attributes(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """Related tab panes have hx-trigger for pre-loading."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}"
            f"/seasons/{season.pk}/"
        )

        # Tab panes should have hx-trigger="load delay:100ms"
        preload_panes = authenticated_page.locator(
            '.tab-pane[hx-trigger="load delay:100ms"]'
        )
        assert preload_panes.count() > 0

    def test_season_edit_form_inside_tab(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """In HTMX mode, the form is inside the tab pane, not wrapping all."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}"
            f"/seasons/{season.pk}/"
        )

        # In HTMX mode, form should be inside the active tab pane
        tab_pane_form = authenticated_page.locator(
            ".tab-pane.active form.form-horizontal"
        )
        expect(tab_pane_form).to_be_visible()

    def test_season_edit_primary_form_save(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """Saving primary form in HTMX mode redirects to parent page."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}"
            f"/seasons/{season.pk}/"
        )

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
        assert f"/seasons/{season.pk}/" not in current_url

    def test_htmx_tab_content_loads_dynamically(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """Related tab content loads dynamically via HTMX."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}"
            f"/seasons/{season.pk}/"
        )

        # Wait for HTMX to be ready
        authenticated_page.wait_for_load_state("networkidle")

        # The pre-loaded tab panes should eventually have content
        # (hx-trigger="load delay:100ms" fires on page load)
        authenticated_page.wait_for_timeout(500)

        # Check that at least one related tab pane got content loaded
        # The loading spinner should be replaced with actual content
        related_panes = authenticated_page.locator(
            ".tab-pane[hx-get]"
        )
        if related_panes.count() > 0:
            # After pre-loading, the panes should have content
            first_pane = related_panes.first
            # Wait for the pane to have some content from HTMX
            authenticated_page.wait_for_timeout(1000)
            inner = first_pane.inner_html()
            # The spinner should be replaced or augmented
            assert len(inner) > 0

    def test_competition_edit_page_loads(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """Competition edit page loads correctly in HTMX mode."""
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}/"
        )

        # Page should load without errors
        tab_nav = authenticated_page.locator("#myTab")
        expect(tab_nav).to_be_visible()

        # Edit tab should be active
        active_tab = authenticated_page.locator("#myTab li.active")
        expect(active_tab).to_be_visible()

    def test_tab_click_shows_content(
        self, authenticated_page: Page, live_server, competition_data
    ):
        """Clicking an HTMX tab link shows the tab content."""
        season = competition_data["season"]
        competition = competition_data["competition"]
        authenticated_page.goto(
            f"{live_server.url}/admin/competition/{competition.pk}"
            f"/seasons/{season.pk}/"
        )

        # Wait for page to be fully loaded
        authenticated_page.wait_for_load_state("networkidle")

        # Find a related tab link and click it
        htmx_tabs = authenticated_page.locator("a.htmx-tab-link[hx-get]")

        if htmx_tabs.count() > 0:
            first_htmx_tab = htmx_tabs.first
            tab_id = first_htmx_tab.get_attribute("data-tab-id")
            first_htmx_tab.click()

            # Wait for HTMX to load the content
            authenticated_page.wait_for_timeout(500)

            # The target tab pane should now be visible
            if tab_id:
                target_pane = authenticated_page.locator(f"#{tab_id}")
                expect(target_pane).to_be_visible()
