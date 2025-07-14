This is a Python based repository, it provides a Django reusable application that provides several building blocks for operating a website for sporting clubs.

## Code Standards

### Required Before Each Commit

- Run `uvx isort` and `uvx black` before committing any changes to ensure proper code formatting

### Development Flow

- Test: `uvx tox` to run the full test suite

## Repository Structure

- `touchtechnology/common`: common utilities and helpers
- `touchtechnology/admin`: building blocks for the admin interface
- `touchtechnology/content`: content management features
- `touchtechnology/news`: news articles
- `tournamentcontrol/competition`: sporting competition management
- `tests`: test project to validate the reusable applications
    - each module above has their own set of tests within

## Key Guidelines

1. Follow Django best practices and idiomatic patterns
2. Maintain existing code structure and organization
3. Write unit tests for new functionality.
    - Always use `django-test-plus` style tests.
    - Avoid `assertTrue` and `assertFalse` in favor of `assertEqual` and `assertNotEqual`.
    - Use `assertCountEqual` to check lists and querysets.
4. Use `uvx tox` for running tests across supported Python versions
