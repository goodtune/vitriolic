from django.template.loader import select_template
from test_plus import TestCase

from touchtechnology.admin.forms import AdminFormControlMixin
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


class AdminOwnershipTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)

    def test_dynamic_admin_form_uses_admin_mixin(self):
        # The chunk edit view passes no form_class, so the form is built from
        # AdminComponent.model_form_bases.
        with self.login(self.superuser):
            self.get_check_200("admin:content:chunk:add")
            form = self.last_response.context["form"]
            self.assertIsInstance(form, AdminFormControlMixin)

    def test_mvp_list_templates_live_in_admin(self):
        for name in ("list.html", "list.inc.html", "list.split.inc.html"):
            origin = select_template(["mvp/%s" % name]).origin.name
            self.assertIn("/touchtechnology/admin/templates/mvp/", origin)
