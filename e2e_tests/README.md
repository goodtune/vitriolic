# End-to-End Testing with Playwright

This directory contains the end-to-end testing infrastructure using Playwright for the Visual Scheduler and other dynamic web interface components.

## Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- uv package manager

### Installation

1. Install E2E dependencies:
   ```bash
   uv sync --group e2e
   ```

2. Install Playwright browsers:
   ```bash
   uv run playwright install chromium
   ```

## Running Tests

### Local Development

1. **Quick run (recommended):**
   ```bash
   chmod +x e2e_tests/run_tests.sh
   ./e2e_tests/run_tests.sh
   ```

2. **Manual setup:**
   ```bash
   # Start services
   docker compose -f e2e_tests/docker-compose.yml up -d
   
   # Setup database
   cd e2e_tests
   uv run python manage.py migrate --run-syncdb
   cd ..
   
   # Start Celery worker
   cd tests
   uv run celery -A vitriolic.celery worker --loglevel=info --detach
   cd ..
   
   # Run tests
   uv run pytest e2e_tests/ -v
   
   # Cleanup
   docker compose -f e2e_tests/docker-compose.yml down
   pkill -f "celery.*worker"
   ```

### CI/CD

Tests automatically run in GitHub Actions on push/PR to main/develop branches via the `.github/workflows/e2e-tests.yml` workflow.

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

### Test Environment
- **PostgreSQL**: Database for test data (port 5432)
- **Redis**: Cache and Celery broker (port 6379) 
- **Celery**: Background task processing
- **Django**: Test server with E2E-specific settings

### Browser Configuration
- **Default browser**: Chromium (headless in CI, headed locally)
- **Viewport**: 1920x1080
- **HTTPS**: Ignores SSL errors for local testing

### Database
- **Name**: `vitriolic_e2e`
- **User/Password**: `vitriolic/vitriolic`
- **Host**: `localhost:5432`

## Extending Tests

### Adding New Tests

1. Create test files in `e2e_tests/` following the pattern `test_*.py`
2. Import required fixtures from `conftest.py`
3. Use Playwright's `Page` fixture for browser automation
4. Use `authenticated_page` fixture for tests requiring admin access

### Example Test Structure
```python
def test_my_feature(authenticated_page: Page, live_server_url: str):
    page = authenticated_page
    page.goto(f"{live_server_url}/my-feature/")
    
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

1. **Port conflicts**: Ensure ports 5432 and 6379 are available
2. **Docker issues**: Check Docker daemon is running and has permissions
3. **Browser issues**: Reinstall browsers with `uv run playwright install`
4. **Database issues**: Check PostgreSQL service health and connection

### Debug Mode

Run tests with additional debugging:
```bash
uv run pytest e2e_tests/ -v --tb=long --headed --slowmo=1000
```

### Logs

- **Django logs**: Configure in `e2e_tests/settings.py`
- **Celery logs**: Check worker output
- **Database logs**: Docker compose logs
- **Playwright traces**: Enable in CI artifacts

## Performance Considerations

The E2E tests are designed to help identify and address the Visual Scheduler performance issues mentioned in the original requirement:

1. **Large dataset testing**: Tests with many fields, times, and matches
2. **Drag-and-drop responsiveness**: Measures interaction performance
3. **Memory usage monitoring**: Identifies potential memory leaks
4. **Load time analysis**: Ensures acceptable page load times

These tests provide a baseline for measuring improvements to the Visual Scheduler's performance with very large events.