from unittest import mock

from django.forms import ModelForm
from django.template.loader import select_template
from test_plus import TestCase

from touchtechnology.admin.forms import AdminFormControlMixin
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.forms.mixins import BootstrapFormControlMixin
from touchtechnology.common.tests import factories
from touchtechnology.content.admin import ContentAdminComponent
from touchtechnology.news.admin import NewsAdminComponent


class SomeOtherMixin:
    """A deployment's own form base, standing in for AdminFormControlMixin."""


@per_shell
class FieldTemplateTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)

    def test_admin_edit_uses_admin_field_template(self):
        with self.login(self.superuser):
            self.get_check_200("admin:news:article:add")
            names = [t.name for t in self.last_response.templates]
            self.assertIn(self.shell.field_template, names)
            self.assertNotIn("touchtechnology/common/templatetags/field.html", names)

    def test_public_login_uses_common_field_template(self):
        self.get_check_200("accounts:login")
        names = [t.name for t in self.last_response.templates]
        self.assertIn("touchtechnology/common/templatetags/field.html", names)


@per_shell
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
            origin = select_template([self.shell.template("mvp/%s" % name)]).origin.name
            self.assertIn(
                "/touchtechnology/admin/templates/%s/" % self.shell.template("mvp"),
                origin,
            )

    def test_explicit_form_on_common_mixin_logs_no_error(self):
        # ArticleForm is an explicit form built on the common mixin.
        with self.login(self.superuser):
            with self.assertNoLogs("touchtechnology.common.sites", level="ERROR"):
                self.get_check_200("admin:news:article:add")


class RequiredFormBasesTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)

    def test_defaults_accept_the_common_mixin_in_place_of_the_admin_mixin(self):
        component = NewsAdminComponent.__new__(NewsAdminComponent)
        bases = component.get_required_form_bases()
        self.assertEqual(bases[0], BootstrapFormControlMixin)
        self.assertEqual(bases[1], component.model_form_bases[1])

    def test_overridden_model_form_bases_are_checked_against_themselves(self):
        # The chunk edit view builds its form from model_form_bases.
        with mock.patch.object(
            ContentAdminComponent, "model_form_bases", (SomeOtherMixin, ModelForm)
        ):
            with self.login(self.superuser):
                with self.assertNoLogs("touchtechnology.common.sites", level="ERROR"):
                    self.get_check_200("admin:content:chunk:add")
                form = self.last_response.context["form"]
        self.assertIsInstance(form, SomeOtherMixin)

    def test_form_on_neither_mixin_still_logs_the_error(self):
        # ArticleForm is explicit, on the common mixin and not the other one.
        with mock.patch.object(
            NewsAdminComponent, "model_form_bases", (SomeOtherMixin, ModelForm)
        ):
            with self.login(self.superuser):
                with self.assertLogs(
                    "touchtechnology.common.sites", level="ERROR"
                ) as logs:
                    self.get_check_200("admin:news:article:add")
        self.assertIn("does not inherit", logs.output[0])
        self.assertIn("SomeOtherMixin", logs.output[0])
