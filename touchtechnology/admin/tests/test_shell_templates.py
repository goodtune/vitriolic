import copy
import pathlib
import tempfile

from django.conf import settings
from django.template.loader import render_to_string
from django.test import RequestFactory
from test_plus import TestCase

from touchtechnology.admin.shells import DEFAULT_SHELL, EXPLORER, SHELLS, WORKBOOK
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests import factories

#: The admin pages 4.x shipped at a neutral path, which a deployment's own
#: templates extend: the name they had, and the name the page has in a shell's
#: folder (see ``Shell.template``).
LEGACY_PAGES = {
    "touchtechnology/admin/base.html": "base.html",
    "touchtechnology/admin/list.html": "list.html",
    "touchtechnology/admin/edit.html": "edit.html",
    "40x.html": "40x.html",
}


def deployment_templates(test, templates):
    """
    Settings in which a deployment's template directory, looked in before any
    app's, holds ``templates``: a mapping of template name to its text.
    """
    root = tempfile.TemporaryDirectory()
    test.addCleanup(root.cleanup)
    for name, text in templates.items():
        path = pathlib.Path(root.name, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    configured = copy.deepcopy(settings.TEMPLATES)
    configured[0]["DIRS"] = [root.name]
    return test.settings(TEMPLATES=configured)


@per_shell
class NeutralOverrideTests(TestCase):
    """A template at a shell-neutral path wins over the shell's page there."""

    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)

    def with_template(self, name, text):
        return deployment_templates(self, {name: text})

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
class LegacyNeutralPathTests(TestCase):
    """
    A deployment's template that extends an admin page by the name it had in
    4.x is drawn by the shell the site wears, whichever that is.
    """

    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)

    def test_a_list_extending_the_old_list_is_drawn_by_the_shell(self):
        templates = {
            "touchtechnology/news/admin/article/list.html": (
                '{% extends "touchtechnology/admin/list.html" %}'
                '{% block extracss %}<link rel="stylesheet" href="/deployment/list.css">'
                "{% endblock %}"
            ),
        }
        with deployment_templates(self, templates), self.login(self.superuser):
            self.get_check_200("admin:news:article:list")
            self.assertTemplateUsed(
                self.last_response, self.shell.template("list.html")
            )
            self.assertResponseContains(
                '<link rel="stylesheet" href="/deployment/list.css">'
            )

    def test_the_old_list_does_not_shadow_a_deployments_page_for_the_shell(self):
        templates = {
            self.shell.template("list.html"): (
                '<p class="deployment-shell-list">Our list for the shell</p>'
            ),
        }
        with deployment_templates(self, templates), self.login(self.superuser):
            self.get_check_200("admin:news:article:list")
            self.assertResponseContains(
                '<p class="deployment-shell-list">Our list for the shell</p>'
            )

    def test_an_edit_page_extending_the_old_edit_is_drawn_by_the_shell(self):
        templates = {
            "touchtechnology/news/admin/article/edit.html": (
                '{% extends "touchtechnology/admin/edit.html" %}'
                '{% block extracss %}<link rel="stylesheet" href="/deployment/edit.css">'
                "{% endblock %}"
            ),
        }
        with deployment_templates(self, templates), self.login(self.superuser):
            self.get_check_200("admin:news:article:add")
            self.assertTemplateUsed(
                self.last_response, self.shell.template("edit.html")
            )
            self.assertResponseContains(
                '<link rel="stylesheet" href="/deployment/edit.css">'
            )

    def test_a_page_extending_the_old_base_is_drawn_by_the_shell(self):
        templates = {
            "touchtechnology/news/admin/article/list.html": (
                '{% extends "touchtechnology/admin/base.html" %}'
                '{% block content %}<p class="deployment-page">Our own page</p>'
                "{% endblock %}"
            ),
        }
        with deployment_templates(self, templates), self.login(self.superuser):
            self.get_check_200("admin:news:article:list")
            self.assertTemplateUsed(
                self.last_response, self.shell.template("base.html")
            )
            self.assertResponseContains('<p class="deployment-page">Our own page</p>')
            self.assertResponseContains(
                self.by_shell(
                    workbook='<a class="wb-skip" href="#main">Skip to the page</a>',
                    explorer='<a class="skip-link" href="#main">Skip to content</a>',
                )
            )

    def test_a_public_error_page_extending_the_old_40x_is_drawn_by_the_shell(self):
        # The page of a deployment's public site, which the root 404 handler
        # renders. The test signs in as staff so that the shell can draw the
        # admin's navigation.
        templates = {
            "404.html": (
                '{% extends "40x.html" %}'
                "{% block error-code %}404{% endblock %}"
                '{% block error-details %}<p class="deployment-lost">Not here</p>'
                "{% endblock %}"
            ),
        }
        with deployment_templates(self, templates), self.login(self.superuser):
            # There is no name for an address that nothing answers.
            self.get("/no/such/page/")
            self.assert_http_404_not_found()
            self.assertTemplateUsed(self.last_response, self.shell.template("40x.html"))
            self.assertInHTML(
                '<p class="deployment-lost">Not here</p>', self.last_response.text
            )
            self.assertInHTML(
                self.by_shell(
                    workbook='<p class="wb-error-code">404</p>',
                    explorer='<p class="code">404</p>',
                ),
                self.last_response.text,
            )


class LegacyNeutralPathShellTests(TestCase):
    """
    The pages kept at their 4.x names extend the page of the shell that the
    context names, and of the default shell when it names none.
    """

    def stand_ins(self):
        # A page in each shell's folder in place of the real one, saying which
        # shell's page the old name extended.
        return {
            shell.template(page): "%s %s" % (shell.name, page)
            for shell in SHELLS.values()
            for page in LEGACY_PAGES.values()
        }

    def test_the_shell_in_the_context_chooses_the_page(self):
        with deployment_templates(self, self.stand_ins()):
            for shell in SHELLS.values():
                for legacy, page in LEGACY_PAGES.items():
                    with self.subTest(shell=shell.name, template=legacy):
                        self.assertEqual(
                            render_to_string(legacy, {"shell": shell}),
                            "%s %s" % (shell.name, page),
                        )

    def test_the_default_shell_draws_the_page_when_the_context_names_none(self):
        with deployment_templates(self, self.stand_ins()):
            for legacy, page in LEGACY_PAGES.items():
                with self.subTest(template=legacy):
                    self.assertEqual(
                        render_to_string(legacy, {}),
                        "%s %s" % (DEFAULT_SHELL, page),
                    )


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


@per_shell
class FileManagerTests(TestCase):
    def test_the_file_list_renders(self):
        user = factories.UserFactory.create(is_staff=True, is_superuser=True)
        # The manager lists the storage's folder, which must exist.
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        with self.settings(MEDIA_ROOT=media.name), self.login(user):
            self.get_check_200("admin:content:media:list")
