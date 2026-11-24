from django.contrib.auth.views import redirect_to_login
from django.test import override_settings
from test_plus import TestCase

from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests import factories


@per_shell
class AdminLoginTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(
            username="admin", is_staff=True, is_superuser=True
        )

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND=None)
    def test_login_page_renders(self):
        self.get_check_200("admin:login")
        self.assertTemplateUsed(self.last_response, self.shell.template("login.html"))
        for fragment in self.by_shell(
            workbook=(
                '<div class="wb-gate-brand"><img src="/static/img/logo.png" alt="">'
                "<span>Administration</span></div>",
                '<button type="submit" class="wb-button wb-button-primary">Sign in</button>',
            ),
            explorer=(
                "<h1>Sign in</h1>",
                '<p class="lede">to the administration of Administration</p>',
                '<button type="submit" class="button primary">Sign in</button>',
            ),
        ):
            self.assertResponseContains(fragment)

    @override_settings(LOGIN_URL="admin:login")
    def test_anonymous_admin_index_redirects_to_admin_login(self):
        self.assertLoginRequired("admin:index")

    def test_login_without_next_lands_on_the_admin(self):
        self.post("admin:login", data={"username": "admin", "password": "password"})
        self.assert_http_302_found(url=self.reverse("admin:index"))

    def test_login_follows_next(self):
        target = self.reverse("admin:news:article:list")
        self.post(
            "admin:login",
            data={"username": "admin", "password": "password", "next": target},
        )
        self.assert_http_302_found(url=target)

    def test_login_refuses_offsite_next(self):
        self.post(
            "admin:login",
            data={
                "username": "admin",
                "password": "password",
                "next": "https://example.net/",
            },
        )
        self.assert_http_302_found(url=self.reverse("admin:index"))

    def test_logout_requires_post_and_lands_on_login(self):
        with self.login(self.superuser):
            self.get("admin:logout")
            self.assert_http_405_method_not_allowed()
            self.post("admin:logout")
            self.assert_http_302_found(url=self.reverse("admin:login"))

    def test_wrong_password_shows_the_error(self):
        self.post("admin:login", data={"username": "admin", "password": "wrong"})
        self.assert_http_200_ok()
        error = self.last_response.context["form"].non_field_errors()[0]
        self.assertResponseContains(
            self.by_shell(
                workbook=f'<ul class="errorlist"><li>{error}</li></ul>',
                explorer=(
                    '<div class="form-errors" role="alert">'
                    '<svg class="icon" aria-hidden="true" focusable="false">'
                    '<use href="/static/touchtechnology/admin/explorer/img/icons.svg#alert">'
                    f"</use></svg><div><ul><li>{error}</li></ul></div></div>"
                ),
            ),
        )

    def test_signed_in_staff_is_sent_on_from_the_login_page(self):
        target = self.reverse("admin:news:article:list")
        with self.login(self.superuser):
            self.get("admin:login", data={"next": target})
            self.assert_http_302_found(url=target)
            self.get("admin:login")
            self.assert_http_302_found(url=self.reverse("admin:index"))

    def test_signed_in_staff_is_not_sent_back_to_the_login_page(self):
        with self.login(self.superuser):
            self.get("admin:login", data={"next": self.reverse("admin:login")})
            self.assert_http_302_found(url=self.reverse("admin:index"))

    def test_staff_redirect_is_never_cached(self):
        with self.login(self.superuser):
            self.get("admin:login")
        self.assert_http_302_found(url=self.reverse("admin:index"))
        self.assertIn("no-store", self.last_response["Cache-Control"])

    def test_signed_in_non_staff_sees_the_form_with_a_notice(self):
        user = factories.UserFactory.create(username="visitor")
        with self.login(user):
            self.get("admin:login", data={"next": self.reverse("admin:index")})
        self.assert_http_200_ok()
        for fragment in self.by_shell(
            workbook=(
                '<p class="wb-message wb-message-warning signed-in-notice">'
                '<svg class="wb-icon" aria-hidden="true" focusable="false">'
                '<use href="/static/touchtechnology/admin/workbook/icons.svg#triangle-alert">'
                "</use></svg><span>You are signed in as visitor, which cannot use the "
                "administration. Sign in with another account.</span></p>",
                '<button type="submit" class="wb-button wb-button-primary">Sign in</button>',
            ),
            explorer=(
                '<p class="notice signed-in-notice">You are signed in as visitor, '
                "which cannot use the administration. Sign in with another account.</p>",
                '<button type="submit" class="button primary">Sign in</button>',
            ),
        ):
            self.assertResponseContains(fragment)

    def test_signed_in_non_staff_is_not_looped(self):
        user = factories.UserFactory.create(username="visitor")
        with self.login(user):
            self.get("admin:index")
            login = redirect_to_login(self.reverse("admin:index"), "admin:login")
            self.assert_http_302_found(url=login.url)
            self.get("admin:login", data={"next": self.reverse("admin:index")})
            self.assert_http_200_ok()

    def test_signed_in_non_staff_can_switch_to_a_staff_account(self):
        user = factories.UserFactory.create(username="visitor")
        with self.login(user):
            self.post(
                "admin:login",
                data={
                    "username": "admin",
                    "password": "password",
                    "next": self.reverse("admin:index"),
                },
            )
            self.assert_http_302_found(url=self.reverse("admin:index"))
            self.get("admin:index")
            self.assert_http_200_ok()
