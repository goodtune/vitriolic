"""Pytest configuration and fixtures for E2E tests."""
import os
import subprocess
import time
from pathlib import Path

import pytest
from playwright.sync_api import Playwright


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup):
    """Override Django DB setup to use test database with PostgreSQL."""
    pass


@pytest.fixture(scope="session")
def test_environment():
    """Start the test environment with Redis, PostgreSQL, and Celery."""
    # Start docker compose services
    docker_compose_path = Path(__file__).parent / "docker-compose.yml"
    
    # Start services
    subprocess.run(
        ["docker", "compose", "-f", str(docker_compose_path), "up", "-d"],
        check=True,
        capture_output=True
    )
    
    # Wait for services to be ready
    time.sleep(10)
    
    # Start Celery worker in the background
    celery_process = subprocess.Popen(
        ["uv", "run", "celery", "-A", "tests.vitriolic.celery", "worker", "--loglevel=info"],
        cwd=Path(__file__).parent.parent / "tests",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    yield
    
    # Cleanup
    celery_process.terminate()
    celery_process.wait(timeout=10)
    
    subprocess.run(
        ["docker", "compose", "-f", str(docker_compose_path), "down"],
        capture_output=True
    )


@pytest.fixture(scope="session")
def live_server_url(test_environment):
    """Start Django development server for E2E tests."""
    import threading
    import socket
    import django
    from django.core.management import execute_from_command_line
    from django.test.utils import setup_test_environment, teardown_test_environment
    
    # Setup Django
    os.environ['DJANGO_SETTINGS_MODULE'] = 'e2e_tests.settings'
    django.setup()
    
    # Setup test environment
    setup_test_environment()
    
    # Find free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        port = s.getsockname()[1]
    
    # Start Django server in thread
    server_url = f"http://localhost:{port}"
    
    def run_server():
        execute_from_command_line([
            'manage.py', 'runserver', f'localhost:{port}', '--noreload'
        ])
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Wait for server to start
    time.sleep(5)
    
    yield server_url
    
    teardown_test_environment()


@pytest.fixture(scope="session")
def browser_context_args():
    """Configure browser context for E2E tests."""
    return {
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
    }


@pytest.fixture
def admin_user(django_user_model, db):
    """Create an admin user for testing."""
    return django_user_model.objects.create_superuser(
        username="testadmin",
        email="admin@test.com",
        password="testpass123"
    )


@pytest.fixture
def authenticated_page(page, live_server_url, admin_user):
    """Provide a page that's already authenticated as admin."""
    # Login
    page.goto(f"{live_server_url}/admin/login/")
    page.fill('input[name="username"]', admin_user.username)
    page.fill('input[name="password"]', "testpass123")
    page.click('input[type="submit"]')
    page.wait_for_url("**/admin/")
    
    return page