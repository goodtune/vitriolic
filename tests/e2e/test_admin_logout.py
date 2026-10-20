"""
End-to-end validation that the rail's Sign out signs the user out.

Since Django 5.0 the logout view only accepts POST, so a plain link to it
answers 405 Method Not Allowed and leaves the user signed in. Sign out is
therefore a form button, and signing out lands on the admin's sign in. At a
desk it is always on show at the foot of the rail.
"""

from django.urls import reverse
from playwright.sync_api import Page, expect


def test_logout_from_the_profile_menu(
    authenticated_page: Page, live_server, screenshot_dir
):
    page = authenticated_page
    page.set_viewport_size({"width": 1440, "height": 900})

    logout = page.get_by_role("button", name="Sign out")
    expect(logout).to_be_visible()
    page.screenshot(path=screenshot_dir / "admin_logout_menu.png")

    logout.click()
    expect(page).to_have_url(f"{live_server.url}{reverse('admin:login')}")
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()

    # Signed out: the admin asks for a login again.
    page.goto(f"{live_server.url}{reverse('admin:index')}")
    expect(page.locator('input[name="password"]')).to_be_visible()
