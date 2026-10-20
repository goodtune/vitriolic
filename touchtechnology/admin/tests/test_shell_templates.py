import copy
import pathlib
import tempfile

from django.conf import settings
from django.template.loader import render_to_string
from django.test import RequestFactory
from test_plus import TestCase

from touchtechnology.admin.shells import EXPLORER, WORKBOOK
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests import factories


@per_shell
class NeutralOverrideTests(TestCase):
    """A template at a shell-neutral path wins over the shell's page there."""

    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)

    def with_template(self, name, text):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        path = pathlib.Path(root.name, name)
        path.parent.mkdir(parents=True)
        path.write_text(text)
        templates = copy.deepcopy(settings.TEMPLATES)
        templates[0]["DIRS"] = [root.name]
        return self.settings(TEMPLATES=templates)

    def test_a_neutral_template_for_a_model_is_chosen(self):
        with (
            self.with_template(
                "touchtechnology/news/admin/article/edit.html", "NEUTRAL ARTICLE EDIT"
            ),
            self.login(self.superuser),
        ):
            self.get_check_200("admin:news:article:add")
            self.assertResponseContains("NEUTRAL ARTICLE EDIT")
            self.assertTemplateNotUsed(
                self.last_response, self.shell.template("edit.html")
            )

    def test_the_shell_page_is_used_without_one(self):
        with self.login(self.superuser):
            self.get_check_200("admin:news:article:add")
            self.assertTemplateUsed(
                self.last_response, self.shell.template("edit.html")
            )

    def test_a_neutral_template_at_the_admin_level_beats_the_shells(self):
        with (
            self.with_template("touchtechnology/admin/edit.html", "NEUTRAL ADMIN EDIT"),
            self.login(self.superuser),
        ):
            self.get_check_200("admin:news:category:add")
            self.assertResponseContains("NEUTRAL ADMIN EDIT")


@per_shell
class ErrorPageTests(TestCase):
    def render(self, template):
        user = factories.UserFactory.create(is_staff=True, is_superuser=True)
        request = RequestFactory().get("/admin/no/such/page/")
        request.user = user
        return render_to_string(template, {"shell": self.shell}, request=request)

    def test_not_found_is_titled_in_either_shell(self):
        html = self.render(self.shell.not_found_template)
        self.assertRegex(html, r"<title>[^<]*Not found[^<]*</title>")

    def test_forbidden_is_titled_in_either_shell(self):
        html = self.render(self.shell.forbidden_template)
        self.assertRegex(html, r"<title>[^<]*Forbidden[^<]*</title>")


class IconRoleTests(TestCase):
    def test_roles_name_each_shells_own_icons(self):
        self.assertEqual(WORKBOOK.icon("venues"), "map-pin")
        self.assertEqual(EXPLORER.icon("venues"), "venue")
        self.assertEqual(EXPLORER.icon("days"), "season")
        self.assertEqual(EXPLORER.icon("teams"), "team")
        self.assertEqual(EXPLORER.icon("sitemap"), "sitemap")
