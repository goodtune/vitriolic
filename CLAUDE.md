# Claude Code Instructions

## Primary Context Source

**Always read and follow the comprehensive project instructions in `.github/copilot-instructions.md`** which contains:

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

### Running Tests

- Run `tox -l` to list the environments. Pick the latest Django/Python combination.
- Run `tox -e <env>` to run all tests for the environment.
- Run `tox -e <env> -- tournamentcontrol.competition` to run all the tests for that module. You can add more modules.
- Run `tox -e <env> -- tournamentcontrol.competition.tests.test_competition_admin.GoodViewTests.test_competition` to run a specific test.
- You can combine various fragments, but always used full dotted address (ie. `package.module.Class.test_method`) and never path (ie. `package/module.py::Class::test_method`).

## Important Reminders

- Follow existing code patterns and Django idioms
- Always use named URLs and proper template path methods
- Test both positive outcomes and security/permission scenarios
- Use ORM relations instead of manual queries
- Never perform `git add .` - always be explicit about the files you add
- Never make up ways to run the tests, follow the instructions
- Python `import` statements must ALWAYS appear at the head of a file. The ONLY exception is if doing so would create a cycle, but you should try to remove the cycle first
- Never run Python scripts directly using `python script.py` - always use the proper Django management command interface or test framework
- Never try to run Django management commands, this is a library, not a Django project

## Continuous Improvement

**Keep this CLAUDE.md file synchronized with `.github/copilot-instructions.md`** - whenever that file changes structure or content, update this summary to reflect the current guidance and maintain alignment with project standards.
