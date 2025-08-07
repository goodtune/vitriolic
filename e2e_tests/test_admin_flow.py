"""End-to-end tests for admin functionality flow."""
import pytest
from playwright.sync_api import Page, expect


class TestAdminFlow:
    """Test the complete admin workflow as specified in the requirements."""

    def test_admin_login(self, page: Page, live_server, admin_user):
        """Test admin login functionality."""
        page.goto(f"{live_server.url}/admin/login/")
        
        # Check login form is present
        expect(page.locator('input[name="username"]')).to_be_visible()
        expect(page.locator('input[name="password"]')).to_be_visible()
        
        # Login with admin credentials
        page.fill('input[name="username"]', admin_user.username)
        page.fill('input[name="password"]', "testpass123")
        page.click('input[type="submit"]')
        
        # Verify successful login - should redirect to admin dashboard
        expect(page).to_have_url(f"{live_server.url}/admin/")
        expect(page.locator("h1")).to_contain_text("Django administration")

    def test_add_home_page(self, authenticated_page: Page, live_server):
        """Test adding a home page - must be first thing, literally and nothing else."""
        page = authenticated_page
        
        # Navigate to content/page admin
        page.goto(f"{live_server.url}/admin/common/sitemapnode/add/")
        
        # Fill out the home page form
        page.fill('input[name="title"]', "Home")
        page.fill('input[name="slug"]', "home")
        
        # Set as homepage by making parent empty and setting as root
        page.locator('select[name="content_type"]').select_option(label="Page")
        
        # Save the page
        page.click('input[name="_save"]')
        
        # Verify the home page was created
        expect(page).to_have_url("**/admin/common/sitemapnode/")
        expect(page.locator(".success")).to_be_visible()

    def test_add_news_application(self, authenticated_page: Page, live_server):
        """Test adding the news application."""
        page = authenticated_page
        
        # Navigate to add news section
        page.goto(f"{live_server.url}/admin/common/sitemapnode/add/")
        
        # Fill out news application form
        page.fill('input[name="title"]', "News")
        page.fill('input[name="slug"]', "news")
        
        # Select news application content type
        page.locator('select[name="content_type"]').select_option(label="News Application")
        
        # Save
        page.click('input[name="_save"]')
        
        # Verify creation
        expect(page).to_have_url("**/admin/common/sitemapnode/")
        expect(page.locator(".success")).to_be_visible()

    def test_add_article_to_news(self, authenticated_page: Page, live_server):
        """Test adding an article to the news application."""
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

    def test_add_competition_application(self, authenticated_page: Page, live_server):
        """Test adding the competition application."""
        page = authenticated_page
        
        # Navigate to add competition section
        page.goto(f"{live_server.url}/admin/common/sitemapnode/add/")
        
        # Fill out competition application form
        page.fill('input[name="title"]', "Competitions")
        page.fill('input[name="slug"]', "competitions")
        
        # Select competition application content type  
        page.locator('select[name="content_type"]').select_option(label="Competition Application")
        
        # Save
        page.click('input[name="_save"]')
        
        # Verify creation
        expect(page).to_have_url("**/admin/common/sitemapnode/")
        expect(page.locator(".success")).to_be_visible()

    def test_add_competition_structure(self, authenticated_page: Page, live_server):
        """Test adding competition, season, division, team to the competition application."""
        page = authenticated_page
        
        # Step 1: Add Competition
        page.goto(f"{live_server.url}/admin/competition/competition/add/")
        page.fill('input[name="title"]', "Test Competition")
        page.fill('input[name="abbreviation"]', "TC")
        page.click('input[name="_save"]')
        expect(page.locator(".success")).to_be_visible()
        
        # Step 2: Add Season
        page.goto(f"{live_server.url}/admin/competition/season/add/")
        page.locator('select[name="competition"]').select_option(label="Test Competition")
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

    def test_check_sitemap_xml(self, authenticated_page: Page, live_server):
        """Test that sitemap.xml is accessible and contains expected content."""
        page = authenticated_page
        
        # Navigate to sitemap.xml
        page.goto(f"{live_server.url}/sitemap.xml")
        
        # Verify sitemap loads and contains XML content
        content = page.content()
        assert "<?xml" in content
        assert "urlset" in content
        assert live_server.url in content
        
        # Verify it contains the pages we created
        assert "home" in content or "Home" in content