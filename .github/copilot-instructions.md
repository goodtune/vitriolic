This is a Python based repository, it provides a Django reusable application that provides several building blocks for operating a website for sporting clubs.

## Code Standards

### Required Before Each Commit

- Run `isort` and `black` before committing any changes to ensure proper code formatting

### Development Flow

- Test: `tox` to run the full test suite
- Test: `tox -l` to list the available `tox` environments - you can pick one for faster feedback or run them all for thoroughness

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
4. Use `tox` for running tests across supported Python versions
5. **Continuous Improvement**: During any code review iteration, continuously evolve this instructions file to incorporate new guidance and reaffirm established patterns based on reviewer feedback.
    - Use `assertCountEqual` to check lists and querysets.
6. **Imports and Dependencies**: 
    - Never use try/except for imports of required dependencies - imports should be at the head of the file
    - Only use inline imports to avoid circular import issues
7. **Template Conventions**:
    - Use `self.template_path()` method to find templates instead of hardcoding template paths
    - Follow existing patterns for template path construction
8. **URL and Test Conventions**:
    - Always use named URLs in tests with `self.reverse()` instead of hardcoded URL strings
    - Use ORM reverse relations to find related objects instead of manual queries
9. **Permission and Security Guidelines**:
    - Protected views must use the same permission level as related functionality (e.g., stream views)
    - Always test both authorized and unauthorized access to protected endpoints
    - Use `@login_required_m` and `permissions_required()` for consistent security patterns

## Test Writing Best Practices

### Assertion Guidelines
- **Always assert positive expected outcomes** - don't settle for "not failing" tests
- **Avoid intermediate variables** - use assertions directly instead of assigning to temporary variables first
- **Never use `assertIsNotNone()` or `assertNotEqual()`** unless specifically checking for None/inequality
- **Use `assertEqual()` with expected values** - verify exact expected results, not just "anything but X"
- **Test the actual behavior** - ensure tests validate what the code should do, not just that it doesn't crash

### Django Test Plus Patterns
- **User creation**: Use the `make_user()` utility function in combination with the `user_factory` attribute
  - **Admin users**: Set the `user_factory` to `SuperUserFactory`
- **Authentication**: Use `self.login(self.user)` approach 
- **HTTP requests**: Use `self.get(named_url, *args)` instead of direct client calls or manual URL construction
- **Response validation**: Use `self.response_XXX()` to check status codes
- **Content validation**: Use `self.assertResponseContains(...)` to check for HTML fragments
- **URL Testing**: Always use named URLs with `self.reverse("url_name", args...)` - never hardcode URL strings

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
- **No management commands for tests** - use regular unit tests instead
- **Remove utility function calls from integration tests** - test through the actual usage paths
- **Focus on user-facing behavior** - test how features work in practice, not internal implementation details

### Permission Testing
- **Test unauthorized access**: Always verify that protected endpoints require proper authentication
- **Test insufficient permissions**: Check that users without required permissions get 403 responses
- **Test authorized access**: Verify superusers and users with correct permissions can access protected views
- **Use proper test users**: Create `SuperUserFactory` users for admin-level access testing
