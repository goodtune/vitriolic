# Claude Code Instructions

## Primary Context Source

**Always read and follow the comprehensive project instructions in `.github/copilot-instructions.md`** which contains:

- Complete code standards and formatting requirements (`isort`, `black`)
- Repository structure overview (Django reusable apps for sporting clubs)
- Development workflow and testing guidelines (`tox`)
- Detailed Django best practices and patterns
- Comprehensive test writing guidelines using `django-test-plus`
- Security and permission testing requirements
- Model field and admin view testing patterns
- Import organization and positive assertion requirements

## Key Project Context

This is a Django-based repository providing reusable applications for sporting club websites, including:

- Common utilities (`touchtechnology/common`)
- Admin building blocks (`touchtechnology/admin`)
- Content management (`touchtechnology/content`)
- News system (`touchtechnology/news`)
- Competition management (`tournamentcontrol/competition`)

## Test Structure

- **Unit tests**: Use Django test framework with `django-test-plus`, located within each module
- **E2E tests**: Use Playwright with `pytest-django`, located in `tests/e2e/`
- **Execution**: Run via `tox` for full suite or specific environments

## Important Reminders

- Follow existing code patterns and Django idioms
- Always use named URLs and proper template path methods
- Test both positive outcomes and security/permission scenarios
- Use ORM relations instead of manual queries
- Never perform `git add .` - always be explicit about the files you add

## Continuous Improvement

**Keep this CLAUDE.md file synchronized with `.github/copilot-instructions.md`** - whenever that file changes structure or content, update this summary to reflect the current guidance and maintain alignment with project standards.