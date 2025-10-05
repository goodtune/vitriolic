from django.test import override_settings
from test_plus import TestCase


class APIPermissionsTestCase(TestCase):
    """Test that API root views work with various permission configurations"""

    def test_api_root_accessible_by_anonymous_users(self):
        """Test that /api/ root is accessible by anonymous users"""
        self.get("api-root")
        self.response_200()

    def test_api_v1_accessible_by_anonymous_users(self):
        """Test that /api/v1/ root is accessible by anonymous users"""
        self.get("v1:api-root")
        self.response_200()

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_PERMISSION_CLASSES": [
                "rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly"
            ]
        }
    )
    def test_api_root_with_django_model_permissions_or_anon_read_only(self):
        """
        Test that /api/ root works even when DjangoModelPermissionsOrAnonReadOnly
        is configured globally. This permission class requires a queryset, but
        API root views don't have querysets since they just list endpoints.
        """
        self.get("api-root")
        self.response_200()

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_PERMISSION_CLASSES": [
                "rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly"
            ]
        }
    )
    def test_api_v1_with_django_model_permissions_or_anon_read_only(self):
        """
        Test that /api/v1/ root works even when DjangoModelPermissionsOrAnonReadOnly
        is configured globally. This permission class requires a queryset, but
        API root views don't have querysets since they just list endpoints.
        """
        self.get("v1:api-root")
        self.response_200()
