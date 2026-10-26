This is a Python based repository, it provides a Django reusable application that provides several building blocks for operating a website for sporting clubs.

## Code Standards

### Development Flow

- **Unit Tests**: `tox` to run the full unit test suite across Django/Python versions
- **E2E Tests**: `tox -e e2e` to run end-to-end browser tests with Playwright
- **Environment Options**: `tox -l` to list available `tox` environments - pick specific ones for faster feedback or run all for thoroughness

## Repository Structure

- `touchtechnology/common`: common utilities and helpers
- `touchtechnology/admin`: building blocks for the admin interface
- `touchtechnology/content`: content management features
- `touchtechnology/news`: news articles
- `tournamentcontrol/competition`: sporting competition management
- Tournament Ops site (`tournamentcontrol/competition/compops`, see `docs/compops.md`)
- `tests`: test project and infrastructure to validate the reusable applications
    - **Unit tests**: Each module above has their own set of tests using Django test framework with `django-test-plus`
    - **E2E tests**: Located in `tests/e2e/` using Playwright with `pytest-django` for browser automation and admin workflow testing

## Key Guidelines

1. Follow Django best practices and idiomatic patterns
2. Maintain existing code structure and organization
3. Write unit tests for new functionality.
    - Always use `django-test-plus` style tests.
    - Avoid `assertTrue` and `assertFalse` in favor of `assertEqual` with the expected value. `assertNotEqual` is not a substitute; see the Assertion Guidelines below.
    - Use `assertCountEqual` to check lists and querysets.
4. Use `tox` for running tests across supported Python versions
    - Before opening a PR, run the environment with no selector (`tox -e <env>` alone), as CI does. Module order changes what leaks between tests, so a module that passes on its own can fail in the full run.
5. **Continuous Improvement**: During any code review iteration, continuously evolve this instructions file to incorporate new guidance and reaffirm established patterns based on reviewer feedback. **When updating this file, also update `CLAUDE.md` to maintain synchronization with the summary overview.**
6. **Imports and Dependencies**: 
    - **All imports must be at the head of the file** - never place import statements inside functions or methods
    - Never use try/except for imports of required dependencies - imports should be at the head of the file
    - Only use inline imports to avoid circular import issues
7. **String Building and Logging**:
    - Build strings with f-strings, never `%` or `.format()`, with three exceptions:
        - Logger calls take printf-style lazy arguments: `logger.info("Message with %s and %s", var1, var2)` not `logger.info(f"Message with {var1} and {var2}")`, so the message is only formatted when it is emitted
        - SQL placeholders stay as `%s` for the database driver to fill in
        - Translatable strings are passed to `_()` with their placeholders intact, and formatted afterwards, so the catalogue entry is stable
    - Modernise `%`, `.format()` and `super(Class, self)` only in files the PR already modifies; do not open unrelated files to do it
8. **Template Conventions**:
    - Use `self.template_path()` method to find templates instead of hardcoding template paths
    - Follow existing patterns for template path construction
9. **URL and Test Conventions**:
    - Always use named URLs in tests with `self.reverse()` instead of hardcoded URL strings
    - Use ORM reverse relations to find related objects instead of manual queries
10. **Permission and Security Guidelines**:
    - Protected views must use the same permission level as related functionality (e.g., stream views)
    - Always test both authorized and unauthorized access to protected endpoints
    - Admin views: decorate with `@staff_login_required_m` (`touchtechnology/common/decorators.py`) and pass `permission_required=True` to the `generic_*` view (`generic_list`, `generic_edit`, `generic_delete`, ...), which checks the model's permissions, global or on the object, with `django-guardian`
    - A view that does not end in a `generic_*` view checks with `guardian.utils.get_40x_or_None`, as `_confirm_youtube_destroyed` in `tournamentcontrol/competition/admin.py` does
    - CompOps views use `staff_required` and the checks in `tournamentcontrol/competition/compops/permissions.py`

## Test Writing Best Practices

### Assertion Guidelines
- **Always assert positive expected outcomes** - don't settle for "not failing" tests or negative assertions
- **No ambiguous testing** - all responses must be predictable, assert for exact expected values, not what should not happen
- **Avoid intermediate variables** - use assertions directly instead of assigning to temporary variables first
- **Never use `assertIsNotNone()`, `assertNotEqual()`, or `!= 404`** - assert for the specific expected value instead; this is why item 3 above does not offer `assertNotEqual` as an alternative to `assertFalse`
- **Use `assertEqual()` with expected values** - verify exact expected results, not just "anything but X"
- **Test the actual behavior** - ensure tests validate what the code should do, not just that it doesn't crash

### Django Test Plus Patterns
- **User creation**: Use the `make_user()` utility function in combination with the `user_factory` attribute
  - **Admin users**: Set the `user_factory` to `SuperUserFactory`
- **Authentication**: Use `self.login(self.user)` approach
- **HTTP requests**: Use `self.get(named_url, *args)` instead of direct client calls or manual URL construction
  - **No assigned response**: never write `response = self.get(...)`; the helpers below read `self.last_response` themselves
  - `self.get_check_200("url_name", *args)` fetches and checks the status in one call
- **Response validation**: Use `self.assert_http_###_name()` to check status codes (`self.assert_http_200_ok()`, `self.assert_http_403_forbidden()`, ...); never read `.status_code` yourself
  - **Redirects**: `self.assert_http_302_found(url=...)`, not `assertRedirects`
  - **Login required**: `self.assertLoginRequired("url_name", *args)`
  - **Headers**: `self.assertResponseHeaders({"Header": "value"})`
- **Content validation**: Use `self.assertResponseContains(...)` to check for HTML fragments
  - **Always assert a full HTML fragment** (e.g. the whole `<td>` or `<input>` element) and never pass an `html=` argument; `html=False` searches for bare text, which can keep matching after a regression because the text appears somewhere unrelated on the page
- **URL Testing**: Always use named URLs with `self.reverse("url_name", args...)` - never hardcode URL strings
  - `self.reverse()` passes every keyword argument on as a URL kwarg, so it cannot take `query=`; for a query string use `from django.urls import reverse` and `reverse("url_name", query={...})`

### Model Field Guidelines
- **UndecidedTeam models**: Don't set both `label` and `formula` - use one or the other as per form validation
- **Eval fields**: When testing any `eval` fields, verify both admin rendering and direct method calls
- **All outcomes testing**: Test all possible outcomes - both valid scenarios (that resolve correctly) and invalid scenarios (that degrade gracefully)

### Admin View Testing
- **Test real usage**: Set up actual model objects and call admin views to force evaluation
- **Verify rendering**: Check that both valid and invalid data render appropriately
- **Check specific content**: Don't just verify page loads - confirm expected titles/content appear

### Error Handling Testing
- **Test graceful degradation**: Verify that invalid data doesn't crash but provides meaningful fallbacks
- **Verify exact error states**: When testing error conditions, assert the specific error content expected
- **Test method return values**: Understand and test what methods actually return (tuples, dicts, etc.)

### Test Organization
- **Class-level data goes in `setUpTestData`** - never override `setUpClass`; if one must be, it has to call `super()` first or the class's transaction is never opened
- **No management commands for tests** - use regular unit tests instead
- **Remove utility function calls from integration tests** - test through the actual usage paths
- **Focus on user-facing behavior** - test how features work in practice, not internal implementation details

### Permission Testing
- **Test unauthorized access**: Always verify that protected endpoints require proper authentication
- **Test insufficient permissions**: Check that users without required permissions get 403 responses
- **Test authorized access**: Verify superusers and users with correct permissions can access protected views
- **Use proper test users**: Create `SuperUserFactory` users for admin-level access testing

## E2E Testing Best Practices

### Playwright Test Structure
- **Location**: All E2E tests in `tests/e2e/` directory
- **Shared fixtures**: Use `tests/e2e/conftest.py` for common fixtures like `admin_user` and `authenticated_page`
- **Execution**: Run via `tox -e e2e` which handles browser installation and database setup

### E2E Test Guidelines  
- **Comprehensive docstrings**: All E2E test methods must have detailed docstrings explaining purpose, prerequisites, expected behavior, and current limitations
- **Test real workflows**: Focus on complete user journeys through the admin interface and frontend
- **Performance validation**: Include tests for Visual Scheduler performance with large datasets
- **Browser automation**: Use Playwright's `Page` fixture for browser interactions and `expect()` for assertions
- **Admin delete routes**: a new delete route in the admin needs a `Case` in `tests/e2e/admin_delete.py` saying what its confirmation reads; `test_every_delete_route_has_a_case` in `tests/e2e/test_admin_delete_modals.py` fails until it has one

### E2E Test Patterns
- **Authentication**: Use `authenticated_page` fixture for tests requiring admin access
- **Navigation**: Test complete workflows from login through task completion
- **Error handling**: Verify graceful degradation and user-friendly error messages
- **Cross-browser**: Tests run in Chromium by default, can be configured for other browsers
