# End-to-End Testing with Playwright

This directory contains the end-to-end testing infrastructure using Playwright for the Visual Scheduler and other dynamic web interface components, integrated with the project's tox infrastructure.

## Setup

### Prerequisites

- Python 3.11+
- tox package manager
- uv package manager

### Installation

Install tox if not already available:
```bash
uv tool install tox
```

## Running Tests

### Local Development (Recommended)

**Single command** - run all E2E tests:
```bash
tox -e e2e
```

**Run specific tests:**
```bash
tox -e e2e -- test_admin_flow.py -v
```

**Run without slow tests:**
```bash
tox -e e2e -- -m "not slow"
```

### Manual Development Setup

For iterative development, you can also run tests without tox:

1. **Setup environment:**
   ```bash
   uv sync --group e2e --all-extras
   ```

2. **Start services (in background):**
   ```bash
   docker compose up postgres:14-alpine redis:7-alpine -d
   ```

3. **Run tests:**
   ```bash
   cd e2e_tests
   uv run pytest . -v
   ```

4. **Cleanup:**
   ```bash
   docker compose down
   ```

### CI/CD

Tests automatically run in GitHub Actions via tox integration in the project's CI workflow.

## Test Structure

### Core Admin Flow Tests (`test_admin_flow.py`)
- **Admin login**: Verifies admin authentication
- **Add home page**: Tests creating the root home page (required first step)  
- **Add news application**: Tests adding news functionality
- **Add article**: Tests creating news articles
- **Add competition application**: Tests adding competition functionality
- **Add competition structure**: Tests creating competition/season/division/team hierarchy
- **Check sitemap.xml**: Validates sitemap generation and accessibility

### Performance Tests (`test_visual_scheduler_performance.py`)
- **Visual Scheduler load time**: Measures page load performance with large datasets
- **Drag and drop performance**: Tests responsiveness of drag-and-drop operations
- **Memory usage**: Monitors browser memory usage during operations

## Configuration

### Test Environment (Managed by tox-docker)
- **PostgreSQL**: Database for test data (port 5432)
- **Redis**: Cache and Celery broker (port 6379) 
- **Django**: Test server using existing project settings via `tests.vitriolic.settings`

### Browser Configuration
- **Default browser**: Chromium (headless in CI, can be headed locally)
- **Viewport**: 1920x1080
- **HTTPS**: Ignores SSL errors for local testing

### Database
- **Name**: Auto-generated test database
- **User/Password**: `vitriolic/vitriolic` (via tox-docker)
- **Host**: `localhost:5432`

## Benefits of Tox Integration

### For Local Development:
- **Single command**: `tox -e e2e` handles everything
- **No manual setup**: No Docker Compose or service management  
- **Isolated environment**: No dependency conflicts
- **Automatic cleanup**: No leftover containers or processes

### For CI/CD:
- **Simplified workflow**: No custom service configuration
- **Better reliability**: Standard tox patterns, proven infrastructure
- **Easier maintenance**: Follows project conventions
- **Consistent results**: Same environment as local development

### For the Codebase:
- **Django best practices**: Uses pytest-django fixtures properly
- **Better maintainability**: Standard pytest-django patterns
- **Scalable**: Easy to add more test environments

## Extending Tests

### Adding New Tests

1. Create test files in `e2e_tests/` following the pattern `test_*.py`
2. Import required fixtures from `conftest.py`
3. Use Playwright's `Page` fixture for browser automation
4. Use `authenticated_page` fixture for tests requiring admin access

### Example Test Structure
```python
def test_my_feature(authenticated_page: Page, live_server):
    page = authenticated_page
    page.goto(f"{live_server.url}/my-feature/")
    
    # Test interactions
    page.click("button")
    expect(page.locator("h1")).to_contain_text("Expected Text")
```

### Performance Testing

For performance-critical tests like the Visual Scheduler:
1. Mark tests with `@pytest.mark.slow`
2. Use appropriate dataset fixtures
3. Measure timing with Playwright's built-in performance APIs
4. Set reasonable performance thresholds

### Test Data Management

- Use Django fixtures and factories for test data
- Create reusable fixtures in `conftest.py`
- Clean up test data between test runs
- Use database transactions where appropriate

## Troubleshooting

### Common Issues

1. **Tox environment issues**: Run `tox -r -e e2e` to recreate environment
2. **Browser issues**: Tox automatically installs Playwright browsers
3. **Database issues**: tox-docker handles PostgreSQL service management
4. **Port conflicts**: tox-docker uses available ports automatically

### Debug Mode

Run tests with additional debugging:
```bash
tox -e e2e -- --headed --slowmo=1000 -v --tb=long
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