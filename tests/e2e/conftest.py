"""Pytest configuration and shared fixtures for E2E tests."""

import os
import socket
import threading
from pathlib import Path

import pytest
import uvicorn
from django.contrib.auth.models import Permission
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.core.asgi import get_asgi_application
from playwright.sync_api import Page


@pytest.fixture(scope="session")
def browser_context_args():
    """Configure browser context for E2E tests."""
    return {
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """
    Allow environments with a pre-installed browser to run the E2E suite
    without downloading one, by pointing PLAYWRIGHT_CHROMIUM_EXECUTABLE at
    the browser binary. CI is unaffected -- it installs the browser
    matching the pinned Playwright version.
    """
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if executable:
        return {**browser_type_launch_args, "executable_path": executable}
    return browser_type_launch_args


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


class AsgiLiveServer:
    """
    uvicorn in a daemon thread, in this process, so the server shares the
    test database and settings exactly as Django's thread-based live
    server does. pytest-django's ``live_server`` is WSGI and would block
    forever on the ops site's endless SSE responses.
    """

    def __init__(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.host, self.port = sock.getsockname()
        sock.close()
        config = uvicorn.Config(
            ASGIStaticFilesHandler(get_asgi_application()),
            host=self.host,
            port=self.port,
            log_level="warning",
            lifespan="off",
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def url(self):
        return f"http://{self.host}:{self.port}"

    def start(self):
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                return
            self.thread.join(0.1)
        raise RuntimeError("ASGI live server did not start")

    def stop(self):
        self.server.should_exit = True
        self.thread.join(5)


@pytest.fixture
def asgi_live_server(transactional_db, settings):
    settings.ALLOWED_HOSTS = ["*"]
    server = AsgiLiveServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def ops_user(django_user_model, transactional_db):
    user = django_user_model.objects.create_user(
        username="ops", password="password", email="ops@test.com", is_staff=True
    )
    user.user_permissions.add(
        *Permission.objects.filter(
            codename__in=[
                "change_match",
                "add_simplescorematchstatistic",
                "change_simplescorematchstatistic",
                "stream_season",
            ]
        )
    )
    return user


def _login(page, base_url, username):
    page.goto(f"{base_url}/accounts/login/")
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', "password")
    page.click("button")
    page.wait_for_load_state("networkidle")


@pytest.fixture
def ops_page(page, asgi_live_server, ops_user):
    _login(page, asgi_live_server.url, "ops")
    return page


@pytest.fixture
def second_page(browser, asgi_live_server, ops_user):
    context = browser.new_context()
    page = context.new_page()
    _login(page, asgi_live_server.url, "ops")
    yield page
    context.close()
