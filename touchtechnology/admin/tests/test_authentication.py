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
            html=True,
        )
        self.assertResponseNotContains("logout.js")
