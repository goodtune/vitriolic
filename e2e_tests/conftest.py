"""Pytest configuration and fixtures for E2E tests."""
import os
import pytest


# Configure Django settings for pytest
def pytest_configure():
    """Configure Django settings for pytest-django."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'e2e_tests.settings')
    
    import django
    from django.conf import settings
    
    # Override test database settings to use PostgreSQL provided by tox-docker
    settings.DATABASES['default'].update({
        'HOST': 'localhost',
        'PORT': '5432',
        'USER': 'vitriolic',
        'PASSWORD': 'vitriolic',
    })
    
    # Override Redis settings to use Redis provided by tox-docker  
    settings.CACHES['default'].update({
        'LOCATION': 'redis://localhost:6379/0',
    })
    
    django.setup()


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
def authenticated_page(page, live_server, admin_user):
    """Provide a page that's already authenticated as admin."""
    # Login
    page.goto(f"{live_server.url}/admin/login/")
    page.fill('input[name="username"]', admin_user.username)
    page.fill('input[name="password"]', "testpass123")
    page.click('input[type="submit"]')
    page.wait_for_url("**/admin/")
    
    return page