import pathlib

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.template.loader import get_template, render_to_string
from django.test import RequestFactory, override_settings
from test_plus import TestCase

import touchtechnology.common
from touchtechnology.admin.shells import EXPLORER, WORKBOOK
from touchtechnology.admin.sites import site
from touchtechnology.admin.templatetags.admin import allowed
from touchtechnology.admin.tests.error_urls import errors_site
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests import factories

ERROR_URLS = "touchtechnology.admin.tests.error_urls"

COMMON_TEMPLATES = pathlib.Path(touchtechnology.common.__file__).parent / "templates"


def admin_before_common():
    """
    ``INSTALLED_APPS`` with ``touchtechnology.admin`` ahead of
    ``touchtechnology.common``, so a template both ship under one name is the
    admin's. The demo project lists them the other way round.
    """
    apps = [app for app in settings.INSTALLED_APPS if app != "touchtechnology.admin"]
    apps.insert(apps.index("touchtechnology.common"), "touchtechnology.admin")
    return apps


class PublicErrorPages:
    """
    What a visitor to the public site is shown when a page is missing or
    refused: the public site's pages, never the admin's, whoever the visitor is
    and whichever of the two apps comes first in ``INSTALLED_APPS``.
    """

    def assertPublicPage(self, code, title):
        self.assertResponseTemplateUsed("http4xx.html")
        self.assertResponseTemplateNotUsed(WORKBOOK.template("base.html"))
        self.assertResponseTemplateNotUsed(EXPLORER.template("base.html"))
        self.assertResponseContains(f"<h1>{code}</h1>", status_code=code)
        self.assertResponseContains(f"<h2>{title}</h2>", status_code=code)

    def test_an_anonymous_visitor_to_an_unknown_address_is_shown_not_found(self):
        # There is no name for an address that nothing answers.
        self.get("/no/such/page/")
        self.assert_http_404_not_found()
        self.assertPublicPage(404, "Page Not Found")

    def test_an_anonymous_visitor_to_a_missing_page_is_shown_not_found(self):
        self.get("missing")
        self.assert_http_404_not_found()
        self.assertPublicPage(404, "Page Not Found")

    def test_a_signed_in_visitor_to_a_missing_page_is_shown_not_found(self):
        user = factories.UserFactory.create()
        with self.login(user):
            self.get("missing")
        self.assert_http_404_not_found()
        self.assertPublicPage(404, "Page Not Found")

    def test_an_anonymous_visitor_to_a_forbidden_page_is_shown_forbidden(self):
        self.get("forbidden")
        self.assert_http_403_forbidden()
        self.assertPublicPage(403, "Forbidden")

    def test_a_signed_in_visitor_to_a_forbidden_page_is_shown_forbidden(self):
        user = factories.UserFactory.create()
        with self.login(user):
            self.get("forbidden")
        self.assert_http_403_forbidden()
        self.assertPublicPage(403, "Forbidden")

    def test_the_error_pages_are_the_common_apps_whichever_app_is_first(self):
        for name in ("403.html", "404.html", "500.html"):
            with self.subTest(name=name):
                self.assertEqual(
                    pathlib.Path(get_template(name).origin.name).resolve(),
                    (COMMON_TEMPLATES / name).resolve(),
                )


@override_settings(ROOT_URLCONF=ERROR_URLS)
class PublicErrorPageTests(PublicErrorPages, TestCase):
    pass


@override_settings(ROOT_URLCONF=ERROR_URLS, INSTALLED_APPS=admin_before_common())
class PublicErrorPagesWithAdminFirstTests(PublicErrorPages, TestCase):
    def test_the_apps_are_in_the_order_the_tests_are_for(self):
        apps = settings.INSTALLED_APPS
        self.assertEqual(
            apps.index("touchtechnology.admin") + 1,
            apps.index("touchtechnology.common"),
        )


class ShellErrorPages:
    """The mark of an error page in each shell, for a test run under either."""

    def error_code(self, code):
        return self.by_shell(
            workbook=f'<p class="wb-error-code">{code}</p>',
            explorer=f'<p class="code">{code}</p>',
        )


@per_shell
@override_settings(ROOT_URLCONF=ERROR_URLS)
class AdminErrorPageTests(ShellErrorPages, TestCase):
    """
    Inside the admin a person who works there is shown the admin's own pages,
    drawn by the shell the admin wears.
    """

    def setUp(self):
        super().setUp()
        previous = errors_site.shell
        errors_site.shell = self.shell_name
        self.addCleanup(setattr, errors_site, "shell", previous)
        self.staff = factories.UserFactory.create(is_staff=True)

    def assertAdminPage(self, code, heading):
        self.assertResponseTemplateUsed(self.shell.template(f"{code}.html"))
        self.assertResponseTemplateNotUsed("http4xx.html")
        self.assertResponseContains(self.error_code(code), status_code=code)
        self.assertResponseContains(f"<h1>{heading}</h1>", status_code=code)

    def assertNotFoundPage(self):
        self.assertAdminPage(
            404,
            self.by_shell(
                workbook="We could not find that page",
                explorer="There is nothing at this address",
            ),
        )

    def assertForbiddenPage(self):
        self.assertAdminPage(403, "You are not permitted to see this")

    def test_staff_are_shown_the_admin_page_for_a_missing_admin_page(self):
        with self.login(self.staff):
            self.get("errors:missing")
        self.assert_http_404_not_found()
        self.assertNotFoundPage()

    def test_staff_are_shown_the_admin_page_for_a_forbidden_admin_page(self):
        with self.login(self.staff):
            self.get("errors:forbidden")
        self.assert_http_403_forbidden()
        self.assertForbiddenPage()

    def test_staff_are_shown_the_admin_page_for_a_missing_object(self):
        # The real admin site, not the one this module adds pages to.
        superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)
        with self.login(superuser):
            self.get("admin:news:article:edit", pk=0)
        self.assert_http_404_not_found()
        self.assertNotFoundPage()

    def test_an_anonymous_visitor_is_shown_the_public_page_not_found(self):
        self.get("errors:missing")
        self.assert_http_404_not_found()
        self.assertResponseTemplateUsed("http4xx.html")
        self.assertResponseContains("<h2>Page Not Found</h2>", status_code=404)

    def test_an_anonymous_visitor_is_shown_the_public_page_forbidden(self):
        self.get("errors:forbidden")
        self.assert_http_403_forbidden()
        self.assertResponseTemplateUsed("http4xx.html")
        self.assertResponseContains("<h2>Forbidden</h2>", status_code=403)

    def test_a_signed_in_visitor_who_is_not_staff_is_shown_the_public_pages(self):
        user = factories.UserFactory.create()
        with self.login(user):
            self.get("errors:missing")
            self.assert_http_404_not_found()
            self.assertResponseTemplateUsed("http4xx.html")
            self.get("errors:forbidden")
            self.assert_http_403_forbidden()
            self.assertResponseTemplateUsed("http4xx.html")

    @override_settings(DEBUG=True)
    def test_debugging_still_shows_the_missing_page_django_describes(self):
        with self.login(self.staff):
            self.get("errors:missing")
        self.assert_http_404_not_found()
        self.assertResponseContains(
            f"<title>Page not found at {self.reverse('errors:missing')}</title>",
            status_code=404,
        )


@per_shell
class AnonymousVisitorTests(ShellErrorPages, TestCase):
    """The admin's pages are drawn without a person to draw them for."""

    def setUp(self):
        super().setUp()
        self.request = RequestFactory().get("/admin/no/such/page/")
        self.request.user = AnonymousUser()

    def test_no_component_is_allowed(self):
        self.assertEqual(allowed(site.get_components(), self.request), [])

    def test_every_component_is_allowed_to_a_superuser(self):
        self.request.user = factories.UserFactory.create(
            is_staff=True, is_superuser=True
        )
        components = site.get_components()
        self.assertCountEqual(allowed(components, self.request), components)

    def test_the_not_found_page_is_drawn(self):
        html = render_to_string(
            self.shell.not_found_template, {"shell": self.shell}, request=self.request
        )
        self.assertInHTML(self.error_code(404), html)

    def test_the_forbidden_page_is_drawn(self):
        html = render_to_string(
            self.shell.forbidden_template, {"shell": self.shell}, request=self.request
        )
        self.assertInHTML(self.error_code(403), html)
