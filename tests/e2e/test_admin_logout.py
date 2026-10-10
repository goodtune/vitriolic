"""
End-to-end validation that the admin's Logout menu entry signs the user out.

Since Django 5.0 the logout view only accepts POST, so a plain link to it
answers 405 Method Not Allowed and leaves the user signed in.
"""

from django.urls import reverse
from playwright.sync_api import Page, expect


def test_logout_from_the_profile_menu(
    authenticated_page: Page, live_server, screenshot_dir
):
    page = authenticated_page

    page.locator(".navbar-profile .dropdown-toggle").click()
    logout = page.get_by_role("link", name="Logout")
    expect(logout).to_be_visible()
    page.screenshot(path=screenshot_dir / "admin_logout_menu.png")

    logout.click()
    expect(page.get_by_text("You have successfully been logged out.")).to_be_visible()

    # Signed out: the admin asks for a login again.
    page.goto(f"{live_server.url}{reverse('admin:index')}")
    expect(page.locator('input[name="password"]')).to_be_visible()
