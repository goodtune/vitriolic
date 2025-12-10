# Testing Infrastructure

This directory is for the testing of this project and covers both unit tests and end-to-end (E2E) or system tests.

## Test Types

### Unit Tests

- **Framework**: Django's built-in test framework with `coverage` and `django-test-plus`
- **Location**: App tests are in the `touchtechnology` and `tournamentcontrol` directories, with `example_app` used to provide models and factories for testing the reusable components.
- **Purpose**: Test individual components, models, views, and business logic
- **Execution**: Run via `tox -e dj{version}-py{version}` (e.g., `tox -e dj52-py311`) for the full suite for a specific Django/Python combination

### End-to-End (E2E) Tests

- **Framework**: Playwright with `pytest-django`
- **Location**: `tests/e2e/` directory for the test definitions
- **Purpose**: Test perform end-to-end user flows, including admin functionality, competition management, and ensure performance is acceptable
- **Execution**: Run via `tox -e e2e` - will run a single Django/Python combination (presently Django 5.2 with Python 3.13) with Chromium browser automation

## Setup

### Prerequisites

- `uv` package manager

## Running Tests

### Run all unit combinations

```bash
uvx tox
```

### Run unit tests for specific Django/Python combination

```bash
uvx tox -e dj52-py311  # Django 5.2 with Python 3.11
uvx tox -e dj42-py312  # Django 4.2 with Python 3.12
uvx tox -e dj60-py314  # Django 6.0 with Python 3.14
```

### Run specific unit test modules with specific Django/Python combination

```bash
uvx tox -e dj52-py311 -- touchtechnology.common
```

### Run all E2E tests

```bash
uvx tox -e e2e
```

### Run specific E2E tests

```bash
uvx tox -e e2e -- e2e/test_admin_flow.py -v
```

### Run E2E tests with browser visible (for debugging)

```bash
uvx tox -e e2e -- --headed --slowmo=1000
```

### CI/CD

Tests automatically run in GitHub Actions via tox integration in the project's CI workflow.

## Test Structure

### Unit Tests Structure

Located in app-specific subdirectories:
- `tests/example_app/tests/` - Example application unit tests
- Unit tests for `touchtechnology.*` and `tournamentcontrol.*` modules
- Use Django's standard test discovery and fixtures

### E2E Tests Structure

The test definitions for programming automated browser interactions are located in `tests/e2e/`.

## Configuration

### Test Environment (Managed by tox-docker)

- **Django**: Test server using existing project settings specified in `tests/vitriolic/settings.py`
- **PostgreSQL**: Database for test data
- **Redis**: Cache and Celery broker

### Browser Configuration

- **Default browser**: Chromium (headless in CI, can be headed locally)
- **Viewport**: 1920x1080
- **HTTPS**: Ignores SSL errors for local testing

### Database

- **Name**: Auto-generated test database
- **User/Password**: `vitriolic/vitriolic` (via tox-docker)
- **Host**: `localhost:5432`

## Benefits of `tox` Integration

### For Local Development

- **Single command**: `tox -e e2e` handles everything
- **No manual setup**: No `docker compose` or service management
- **Isolated environment**: No dependency conflicts
- **Automatic cleanup**: No leftover containers or processes
- **Consistent environment**: Same setup as CI/CD, reducing "it works on my machine" issues

### For CI/CD

- **Simplified workflow**: No custom service configuration
- **Better reliability**: Standard `tox` patterns, proven infrastructure
- **Easier maintenance**: Follows project conventions
- **Consistent results**: Same environment as local development

### For the Codebase

- **Django best practices**: Uses `pytest-django` fixtures properly
- **Better maintainability**: Standard `pytest-django` patterns
- **Scalable**: Easy to add more test environments

## Extending Tests

### Adding New Tests

#### New Unit Tests

1. Create test files in app-specific `tests/` directories
2. Use Django's `TestCase` or `TransactionTestCase` classes
3. Follow Django testing best practices and fixtures

#### New E2E Tests

1. Create test files in `tests/e2e/` following the pattern `test_*.py`
2. Use Playwright's `Page` fixture for browser automation
3. Use `live_server` fixture for Django test server
4. Use `admin_user` fixture for authenticated admin access

### Example Test Structures

#### Unit Test Example

```python
from django.contrib.auth import get_user_model
from test_plus import TestCase
from touchtechnology.common.tests.factories import UserFactory

class MyFeatureTestCase(TestCase):
    user_factory = UserFactory

    def setUp(self):
        self.user = self.make_user()

    def test_my_model_method(self):
        self.assertTrue(self.user.is_active)

    def test_my_view(self):
        self.get("my_view")
        self.response_200()
        self.assertResponseContains("<h1>Expected Heading</h1>")

    def test_my_view_advanced(self):
        self.assertGoodView("my_view")
        self.assertResponseContains("<h1>Expected Heading</h1>")

    def test_protected_view(self):
        self.assertLoginRequired("protected_view")
        with self.login(self.user):
            self.assertGoodView("protected_view")
        self.assertResponseContains("<h1>Protected Content</h1>")
```

#### E2E Test Example

```python
from playwright.sync_api import Page, expect

def test_my_feature(page: Page, live_server, admin_user):
    # Login first, if required
    page.goto(f"{live_server.url}/admin/")
    page.fill('input[name="username"]', "admin")
    page.fill('input[name="password"]', "password")
    page.click("button")

    # Test feature
    page.goto(f"{live_server.url}/my-feature/")
    expect(page.locator("h1")).to_contain_text("Expected Text")
```

## Troubleshooting

### Common Issues

1. **`tox` environment issues**: Run `tox -r -e e2e` to recreate environment
2. **Browser issues**: `tox` automatically installs Playwright browsers
3. **Database issues**: `tox-docker` handles PostgreSQL service management
4. **Port conflicts**: `tox-docker` uses available ports automatically

### Debug Mode

Run tests with additional debugging:

```bash
uvx tox -e e2e -- --headed --slowmo=1000 -v --tb=long
```

### Logs

- **Django logs**: Configured via existing project settings
- **Database logs**: Check tox output for docker logs
- **Playwright traces**: Available in CI artifacts when tests fail

## Performance Considerations

The E2E tests are designed to help identify and address the Visual Scheduler performance issues mentioned in the original requirement:

1. **Large dataset testing**: Tests with many fields, times, and matches
2. **Drag-and-drop responsiveness**: Measures interaction performance
3. **Memory usage monitoring**: Identifies potential memory leaks
4. **Load time analysis**: Ensures acceptable page load times

These tests provide a baseline for measuring improvements to the Visual Scheduler's performance with very large events.
