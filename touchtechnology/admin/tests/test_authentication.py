from unittest import mock

from django.contrib.auth import get_user_model
from test_plus import TestCase

from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests.factories import UserFactory


@per_shell
class AuthenticationTest(TestCase):

    def test_admin_login(self):
        self.get("admin:index")
        self.response_302()

    def test_admin_logout(self):
        user = UserFactory.create(is_staff=True)
        with self.login(user):
            # In Django 5.0 the logout view was changed to not allow GET requests.
            self.post("accounts:logout")
            self.assertResponseContains("<p>You have successfully been logged out.</p>")

    def test_admin_logout_is_a_post_form(self):
        """
        LogoutView refuses GET since Django 5.0, so the menu's Logout is a
        form that posts to the admin's own logout.
        """
        user = UserFactory.create(is_staff=True, is_superuser=True)
        with self.login(user):
            self.get("admin:index")
        self.response_200()
        token = self.get_context("csrf_token")
        logout = self.reverse("admin:logout")
        self.assertResponseContains(
            self.by_shell(
                workbook=(
                    f'<form method="post" action="{logout}">'
                    f'<input type="hidden" name="csrfmiddlewaretoken" value="{token}">'
                    '<button type="submit" class="wb-signout" title="Sign out">'
                    '<svg class="wb-icon" aria-hidden="true" focusable="false">'
                    '<use href="/static/touchtechnology/admin/workbook/icons.svg#log-out">'
                    '</use></svg><span class="wb-me-label">Sign out</span></button></form>'
                ),
                explorer=(
                    f'<form method="post" action="{logout}" class="sign-out">'
                    f'<input type="hidden" name="csrfmiddlewaretoken" value="{token}">'
                    '<button type="submit" class="foot-button" title="Sign out">'
                    '<svg class="icon" aria-hidden="true" focusable="false">'
                    '<use href="/static/touchtechnology/admin/explorer/img/icons.svg#logout">'
                    '</use></svg><span class="foot-label">Sign out</span></button></form>'
                ),
            ),
        )
        self.assertResponseNotContains("logout.js")

    def test_admin_home_greets_user_by_short_name(self):
        """
        The home page greets the user by the user model's informal name,
        ``get_short_name()``. A custom user model can return something other
        than ``first_name``.
        """
        user = UserFactory.create(is_staff=True, is_superuser=True)
        with (
            mock.patch.object(
                get_user_model(), "get_short_name", autospec=True, return_value="Coach"
            ),
            self.login(user),
        ):
            self.get_check_200("admin:index")
        self.assertResponseContains(
            self.by_shell(
                workbook="<h1>Hello, Coach</h1>",
                explorer=(
                    '<p class="kind">'
                    "Good to see you, Coach. Here is what is waiting.</p>"
                ),
            ),
        )

    def test_admin_home_greets_user_without_short_name(self):
        """
        With no short name the workbook says a plain hello and the explorer
        falls back to the username.
        """
        user = UserFactory.create(is_staff=True, is_superuser=True)
        with (
            mock.patch.object(
                get_user_model(), "get_short_name", autospec=True, return_value=""
            ),
            self.login(user),
        ):
            self.get_check_200("admin:index")
        self.assertResponseContains(
            self.by_shell(
                workbook="<h1>Hello</h1>",
                explorer=(
                    '<p class="kind">'
                    f"Good to see you, {user.get_username()}. "
                    "Here is what is waiting.</p>"
                ),
            ),
        )
