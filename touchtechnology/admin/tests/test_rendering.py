from test_plus import TestCase

from touchtechnology.common.tests import factories


class FieldTemplateTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)

    def test_admin_edit_uses_admin_field_template(self):
        with self.login(self.superuser):
            self.get_check_200("admin:news:article:add")
            names = [t.name for t in self.last_response.templates]
            self.assertIn("touchtechnology/admin/templatetags/field.html", names)
            self.assertNotIn("touchtechnology/common/templatetags/field.html", names)

    def test_public_login_uses_common_field_template(self):
        self.get_check_200("accounts:login")
        names = [t.name for t in self.last_response.templates]
        self.assertIn("touchtechnology/common/templatetags/field.html", names)
