"""End-to-end tests for admin functionality flow."""

import pytest
from playwright.sync_api import Page, expect


class TestAdminFlow:
    """Test the complete admin workflow as specified in the requirements."""

    def test_admin_login(self, page: Page, live_server, admin_user):
        """
        Test admin login functionality and dashboard access.

        Validates the complete admin authentication flow including:
        - Login form is properly displayed
        - Authentication with valid credentials succeeds
        - Redirect to admin dashboard occurs
        - Dashboard widgets load correctly

        Prerequisites:
        - Admin user fixture provides valid superuser credentials
        - Django admin interface is properly configured

        Expected behavior:
        - Login form accepts credentials and redirects to /admin/
        - Dashboard displays expected widget titles for tournament management

        Args:
            page: Playwright page fixture
            live_server: Django live server fixture
            admin_user: Admin user fixture
        """
        page.goto(f"{live_server.url}/admin/")

        # Check login form is present
        expect(page.locator('input[name="username"]')).to_be_visible()
        expect(page.locator('input[name="password"]')).to_be_visible()
        expect(page.locator("button")).to_be_visible()

        # Login with admin credentials
        page.fill('input[name="username"]', admin_user.username)
        # We can't read the password from the fixture because it is an actual
        # User instance, so the value of the attribute is the hashed password.
        page.fill('input[name="password"]', "password")
        page.click("button")

        # Verify successful login - should redirect to admin dashboard
        expect(page).to_have_url(f"{live_server.url}/admin/")

        # Check admin dashboard widgets are all loaded
        expect(page.locator('h4[class="portlet-title"]')).to_have_text(
            [
                "Awaiting Scores",
                "Progress Teams",
                "Season Reports",
                "Awaiting Detailed Results",
                "Awaiting MVP Points",
            ]
        )

    def test_add_home_page(self, authenticated_page: Page, live_server):
        """
        Test creating the site's root home page via admin interface.

        This test validates the ability to create the fundamental home page
        that serves as the website's entry point. The home page must be
        created first before other content can be properly structured.

        Prerequisites:
        - Authenticated admin user with content management permissions
        - Common sitemap node admin interface available
        - Page content type available in the system

        Expected behavior:
        - Navigation to sitemap node creation succeeds
        - Form accepts title "Home" and slug "home"
        - Page content type can be selected
        - Save operation completes successfully
        - Success message confirms creation

        Limitations:
        - Currently skipped pending rewrite for actual model structure
        - Requires verification of content management system setup

        Args:
            authenticated_page: Pre-authenticated Playwright page
            live_server: Django live server fixture
        """
        page = authenticated_page

        # Navigate to content management (Sitemap)
        page.goto(f"{live_server.url}/admin/content/")

        new_page = page.get_by_role("link", name="New page")
        expect(new_page).to_be_visible()
        new_page.click()

        # Fill out the home page form
        page.fill('input[name="parent-form-title"]', "Home")
        page.fill('input[name="parent-form-slug"]', "home")

        # Save the page
        page.click('button[type="submit"]')

        # Verify the home page was created
        expect(page).to_have_url(f"{live_server.url}/admin/content/")

        # Verify that a home page link with URL "/" is visible
        site_root = page.get_by_role("link", name="/")
        expect(site_root).to_be_visible()

        # Navigate directly to the root URL to test if the home page is functional
        page.goto(f"{live_server.url}/")

        # Verify that the home page was served (not a 404 or redirect)
        expect(page).to_have_url(f"{live_server.url}/")

    @pytest.mark.skip(reason="Test needs to be rewritten")
    def test_add_news_application(self, authenticated_page: Page, live_server):
        """
        Test adding the news application to the site structure.

        Validates the creation of a news section within the site's navigation
        and content management system. This establishes the foundation for
        publishing news articles and updates.

        Prerequisites:
        - Authenticated admin user with content management permissions
        - News application content type available in system
        - Sitemap node creation interface functional

        Expected behavior:
        - News section can be created with title "News" and slug "news"
        - News Application content type is available for selection
        - Save operation creates the news section successfully
        - Navigation structure updated to include news section

        Limitations:
        - Currently skipped pending verification of news module integration
        - Requires confirmation of content type availability

        Args:
            authenticated_page: Pre-authenticated Playwright page
            live_server: Django live server fixture
        """
        page = authenticated_page

        # Navigate to add news section
        page.goto(f"{live_server.url}/admin/common/sitemapnode/add/")

        # Fill out news application form
        page.fill('input[name="title"]', "News")
        page.fill('input[name="slug"]', "news")

        # Select news application content type
        page.locator('select[name="content_type"]').select_option(
            label="News Application"
        )

        # Save
        page.click('input[name="_save"]')

        # Verify creation
        expect(page).to_have_url("**/admin/common/sitemapnode/")
        expect(page.locator(".success")).to_be_visible()

    @pytest.mark.skip(reason="Test needs to be rewritten")
    def test_add_article_to_news(self, authenticated_page: Page, live_server):
        """
        Test creating and publishing a news article.

        Validates the complete article creation workflow including
        content entry, publication status, and successful save operation.
        This ensures the news system can handle article management.

        Prerequisites:
        - Authenticated admin user with news management permissions
        - News application properly configured and accessible
        - Article model and admin interface available

        Expected behavior:
        - Article creation form accessible at /admin/news/article/add/
        - Title and content fields accept input
        - Published status can be set via checkbox
        - Save operation creates article successfully
        - Confirmation of successful article creation

        Limitations:
        - Currently skipped pending news module setup verification
        - May require additional field validation for complete articles

        Args:
            authenticated_page: Pre-authenticated Playwright page
            live_server: Django live server fixture
        """
        page = authenticated_page

        # Navigate to add article
        page.goto(f"{live_server.url}/admin/news/article/add/")

        # Fill article form
        page.fill('input[name="title"]', "Test News Article")
        page.fill('textarea[name="copy"]', "This is a test news article content.")

        # Set publication status
        page.check('input[name="published"]')

        # Save article
        page.click('input[name="_save"]')

        # Verify creation
        expect(page).to_have_url("**/admin/news/article/")
        expect(page.locator(".success")).to_be_visible()

    @pytest.mark.skip(reason="Test needs to be rewritten")
    def test_add_competition_application(self, authenticated_page: Page, live_server):
        """
        Test adding the competition management application to the site.

        Validates the creation of the competition section that will house
        all tournament-related functionality including competitions, seasons,
        divisions, and teams.

        Prerequisites:
        - Authenticated admin user with content management permissions
        - Competition application content type available
        - Tournament control modules properly installed

        Expected behavior:
        - Competition section creation with title "Competitions" and slug "competitions"
        - Competition Application content type selectable
        - Save operation successfully creates competition section
        - Site navigation updated to include competitions

        Limitations:
        - Currently skipped pending tournament control system verification
        - Requires confirmation of competition module integration

        Args:
            authenticated_page: Pre-authenticated Playwright page
            live_server: Django live server fixture
        """
        page = authenticated_page

        # Navigate to add competition section
        page.goto(f"{live_server.url}/admin/common/sitemapnode/add/")

        # Fill out competition application form
        page.fill('input[name="title"]', "Competitions")
        page.fill('input[name="slug"]', "competitions")

        # Select competition application content type
        page.locator('select[name="content_type"]').select_option(
            label="Competition Application"
        )

        # Save
        page.click('input[name="_save"]')

        # Verify creation
        expect(page).to_have_url("**/admin/common/sitemapnode/")
        expect(page.locator(".success")).to_be_visible()

    @pytest.mark.skip(reason="Test needs to be rewritten")
    def test_add_competition_structure(self, authenticated_page: Page, live_server):
        """
        Test creating the complete competition hierarchy structure.

        Validates the end-to-end creation of a tournament structure including:
        1. Competition - Top-level tournament container
        2. Season - Time-bounded competition period
        3. Division - Competitive grouping within season
        4. Team - Individual competing entity

        This test ensures the hierarchical relationships work correctly
        and that each level can reference its parent properly.

        Prerequisites:
        - Authenticated admin with tournament management permissions
        - Competition, Season, Division, and Team models available
        - Admin interfaces for all tournament entities functional

        Expected behavior:
        - Competition creation with title and abbreviation
        - Season creation linked to competition with year
        - Division creation linked to season with ordering
        - Team creation with basic identification
        - All save operations complete successfully
        - Hierarchical relationships maintained

        Limitations:
        - Currently skipped pending tournament control models verification
        - May require additional validation for competitive integrity
        - Team-division assignment not yet implemented

        Args:
            authenticated_page: Pre-authenticated Playwright page
            live_server: Django live server fixture
        """
        page = authenticated_page

        # Step 1: Add Competition
        page.goto(f"{live_server.url}/admin/competition/competition/add/")
        page.fill('input[name="title"]', "Test Competition")
        page.fill('input[name="abbreviation"]', "TC")
        page.click('input[name="_save"]')
        expect(page.locator(".success")).to_be_visible()

        # Step 2: Add Season
        page.goto(f"{live_server.url}/admin/competition/season/add/")
        page.locator('select[name="competition"]').select_option(
            label="Test Competition"
        )
        page.fill('input[name="title"]', "2024 Season")
        page.fill('input[name="year"]', "2024")
        page.click('input[name="_save"]')
        expect(page.locator(".success")).to_be_visible()

        # Step 3: Add Division
        page.goto(f"{live_server.url}/admin/competition/division/add/")
        page.locator('select[name="season"]').select_option(label="2024 Season")
        page.fill('input[name="title"]', "Division 1")
        page.fill('input[name="abbreviation"]', "D1")
        page.click('input[name="_save"]')
        expect(page.locator(".success")).to_be_visible()

        # Step 4: Add Team
        page.goto(f"{live_server.url}/admin/competition/team/add/")
        page.fill('input[name="title"]', "Test Team")
        page.fill('input[name="abbreviation"]', "TT")
        page.click('input[name="_save"]')
        expect(page.locator(".success")).to_be_visible()
