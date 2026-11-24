"""
End-to-end validation that the admin user list shows when each user registered
and when they last logged in.

On a desktop both dates are shown. On a phone the registration date makes way
and the last login stays, as that is the one an administrator looks for when
deciding whether an account is still in use.
"""

from datetime import datetime, timezone

import pytest
from django.urls import reverse
from playwright.sync_api import Page, expect

DESKTOP = {"width": 1920, "height": 1080}
PHONE = {"width": 390, "height": 844}


@pytest.fixture
def users(django_user_model, db):
    """One user who has logged in since registering, and one who never has."""
    veteran = django_user_model.objects.create_user(
        username="veteran",
        first_name="Alex",
        last_name="Moreau",
        email="alex.moreau@example.com",
        date_joined=datetime(2018, 7, 10, 12, 0, tzinfo=timezone.utc),
        last_login=datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc),
    )
    newcomer = django_user_model.objects.create_user(
        username="newcomer",
        first_name="Jordan",
        last_name="Fairweather",
        email="jordan.fairweather@example.com",
        date_joined=datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc),
    )
    return veteran, newcomer


def _open_user_list(page: Page, live_server) -> None:
    page.goto(f"{live_server.url}{reverse('admin:auth:users:list')}")
    expect(page.get_by_role("columnheader", name="Last login")).to_be_visible()


def _row(page: Page, name: str):
    return page.locator("tr", has_text=name)


class TestAdminUserList:
    def test_desktop_shows_registration_and_last_login(
        self, authenticated_page, live_server, users, screenshot_dir
    ):
        page = authenticated_page
        page.set_viewport_size(DESKTOP)
        _open_user_list(page, live_server)

        expect(page.get_by_role("columnheader", name="Registered")).to_be_visible()
        expect(page.get_by_role("columnheader", name="Last login")).to_be_visible()

        veteran = _row(page, "Alex Moreau").locator("td")
        expect(veteran.nth(1)).to_have_text("10 Jul 2018")
        expect(veteran.nth(2)).to_have_text("19 Sep 2026")

        newcomer = _row(page, "Jordan Fairweather").locator("td")
        expect(newcomer.nth(1)).to_have_text("3 Sep 2026")
        expect(newcomer.nth(2)).to_have_text("Never")

        page.screenshot(path=screenshot_dir / "admin_user_list_desktop.png")

    def test_phone_keeps_last_login_and_drops_registration(
        self, authenticated_page, live_server, users, screenshot_dir
    ):
        page = authenticated_page
        page.set_viewport_size(PHONE)
        _open_user_list(page, live_server)

        expect(page.get_by_role("columnheader", name="Registered")).to_be_hidden()
        expect(page.get_by_role("columnheader", name="Last login")).to_be_visible()

        veteran = _row(page, "Alex Moreau").locator("td")
        expect(veteran.nth(1)).to_be_hidden()
        expect(veteran.nth(2)).to_have_text("19 Sep 2026")

        newcomer = _row(page, "Jordan Fairweather").locator("td")
        expect(newcomer.nth(2)).to_have_text("Never")

        page.screenshot(path=screenshot_dir / "admin_user_list_phone.png")
