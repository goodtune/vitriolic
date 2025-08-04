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

### Admin Integration Testing
- **Test admin URL resolution**: Verify that nested admin URLs resolve correctly
- **Test form rendering**: Ensure admin forms render without AttributeError on foreign key fields
- **Test field choices**: Verify that dropdown fields show appropriate options only
- **Test permission inheritance**: Ensure nested admin views respect parent model permissions

## Admin Integration for Nested Models

When adding new models that are related to existing admin hierarchies, follow these patterns:

### 1. URL Namespace Integration
- **Nested URL patterns**: Add URL patterns within the parent model's URL structure
- **Example**: For `MatchEvent` under `Match`, add URLs at `match/<int:match_id>/matchevent/`
- **Pattern**: Always include the parent model's namespace in the URL hierarchy

```python
# In admin.py get_urls() method
matchevent_urls = (
    [
        path("add/", self.edit_matchevent, name="add"),
        path("<int:pk>/", self.edit_matchevent, name="edit"),
        path("<int:pk>/delete/", self.delete_matchevent, name="delete"),
    ],
    self.app_name,
)

# Include in parent URLs
path(
    "<int:match_id>/matchevent/",
    include(matchevent_urls, namespace="matchevent"),
),
```

### 2. Signal Handler Integration
- **Import requirements**: Always add new signal handlers to `signals/__init__.py` imports
- **Registration**: Connect signals in the app's `ready()` method in `apps.py`
- **Example pattern**:

```python
# In signals/__init__.py
from .matches import match_event_saved_handler  # Add new handlers

# In apps.py ready() method
post_save.connect(match_event_saved_handler, sender=MatchEvent)
```

### 3. Custom Form Requirements for Related Models
When models have foreign keys to other models with custom display requirements:

- **Always create dedicated forms** for admin views instead of using `form_fields`
- **Handle `label_from_instance` properly** - use callable functions, not strings
- **Limit querysets** to relevant objects only for security and UX

```python
class MatchEventForm(BootstrapFormControlMixin, ModelForm):
    player = ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        label_from_instance=lambda person: person.get_full_name,  # Use property, not method
        empty_label="Select player...",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit to match participants only
        if self.instance and self.instance.match_id:
            # Filter querysets based on context
```

### 4. Model Display Method Requirements
- **Properties vs Methods**: Check if display methods are `@property` or callable methods
- **String representation**: Ensure `__str__` methods exist for form dropdown display
- **Label methods**: Use appropriate callable patterns in `label_from_instance`

### 5. Import Integration Checklist
When adding new models to existing modules:

- [ ] Add model to `models.py` imports in `forms.py`
- [ ] Add form to imports in `admin.py`
- [ ] Add signal handlers to `signals/__init__.py`
- [ ] Update admin URL patterns
- [ ] Test admin views work without AttributeError/NoReverseMatch

### 6. TouchTechnology Admin Hierarchy System

**⚠️ Critical Understanding: Automatic Admin Hierarchy Construction**

The `touchtechnology.admin` system automatically builds admin hierarchies based on foreign key relationships between models. This can cause unexpected behavior when models have foreign keys to entities in different admin contexts.

**Key Behavior:**
- `touchtechnology.admin` automatically creates navigation paths between related models
- If Model A has a foreign key to Model B, the admin may try to show Model A objects in Model B's admin context
- This can trigger `NoReverseMatch` errors when trying to generate URLs for models in the wrong admin hierarchy

**Example Problem:**
```python
class MatchEvent(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    team_association = models.ForeignKey(TeamAssociation, on_delete=models.CASCADE)
    # This creates automatic admin links from TeamAssociation to MatchEvent
```

**Solution: Disable Unwanted Reverse Relationships**
Use `related_name="+"` to prevent the admin system from creating automatic reverse relationships:

```python
class MatchEvent(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    team_association = models.ForeignKey(
        TeamAssociation,
        on_delete=models.CASCADE,
        related_name="+"  # Prevents automatic admin hierarchy
    )
```

**When to Use `related_name="+"`:**
- When the foreign key is for data integrity only, not navigation
- When the related model should NOT automatically show the referencing model in its admin
- When you want to control exactly which admin contexts show which related objects

**Debugging Hierarchy Issues:**
1. **Symptom**: `NoReverseMatch` errors mentioning model namespaces in unexpected contexts
2. **Cause**: `touchtechnology.admin` trying to create admin links through foreign key relationships
3. **Solution**: Add `related_name="+"` to foreign keys that shouldn't create admin hierarchy
4. **Verification**: Check that the model only appears in its intended admin context

### 7. Things to Watch Out For

**⚠️ Common Pitfalls:**
1. **Missing signal imports**: `ImportError: cannot import name 'handler_name'`
2. **URL namespace errors**: `NoReverseMatch: 'modelname' is not a registered namespace`
3. **Form field display errors**: `AttributeError: 'Model' object has no attribute 'name'`
4. **Security issues**: Using `Model.objects.all()` instead of contextual filtering
5. **Property vs method confusion**: Using `obj.method()` when it's a `@property`
6. **Automatic admin hierarchy conflicts**: Foreign keys creating unwanted admin navigation paths in `touchtechnology.admin`

**🔍 Debug Steps:**
1. Check `signals/__init__.py` has all required imports
2. Verify URL patterns include proper `namespace` parameter
3. Test form fields render correctly with appropriate `label_from_instance`
4. Ensure querysets are filtered to relevant objects only
5. Confirm model properties/methods are called correctly (with/without parentheses)
6. **For hierarchy issues**: Check if `NoReverseMatch` occurs in unexpected admin contexts, add `related_name="+"` to foreign keys that shouldn't create admin navigation in `touchtechnology.admin`
