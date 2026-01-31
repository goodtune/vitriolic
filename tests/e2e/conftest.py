"""Pytest configuration and shared fixtures for E2E tests."""

import os
from pathlib import Path
import pytest
from playwright.sync_api import Page


@pytest.fixture(scope="session")
def browser_context_args():
    """Configure browser context for E2E tests."""
    return {
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
    }


@pytest.fixture(scope="session")
def screenshot_dir():
    """
    Create and return the directory for storing test screenshots.
    
    Returns:
        Path: Directory path for screenshots
    """
    # Use environment variable if set (for CI), otherwise use local dir
    base_dir = os.environ.get("SCREENSHOTS_DIR", "screenshots")
    screenshots_path = Path(base_dir)
    screenshots_path.mkdir(parents=True, exist_ok=True)
    return screenshots_path


@pytest.fixture
def admin_user(django_user_model, db):
    """
    Create an admin user for testing.

    Returns:
        User: A superuser with username 'admin' and password 'password'
    """
    return django_user_model.objects.create_superuser(
        username="admin",
        password="password",
        email="admin@test.com",
    )


@pytest.fixture
def authenticated_page(page: Page, live_server, admin_user):
    """
    Provide a page that's already authenticated as admin.

    This fixture automatically logs in the admin user and returns
    a page ready for authenticated admin operations.

    Args:
        page: Playwright page fixture
        live_server: Django live server fixture
        admin_user: Admin user fixture

    Returns:
        Page: Authenticated Playwright page object
    """
    # Navigate to admin login
    page.goto(f"{live_server.url}/admin/")

    # Fill login form
    page.fill('input[name="username"]', "admin")
    page.fill('input[name="password"]', "password")
    page.click("button")

    # Wait for successful login redirect
    page.wait_for_url(f"{live_server.url}/admin/")

    return page
