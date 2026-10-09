from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory


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
        LogoutView refuses GET since Django 5.0, so the menu's Logout link
        carries the CSRF token for logout.js to post it.
        """
        user = UserFactory.create(is_staff=True, is_superuser=True)
        with self.login(user):
            self.get("admin:index")
        self.response_200()
        token = self.get_context("csrf_token")
        self.assertResponseContains(
            f'<a href="{self.reverse("accounts:logout")}" data-logout="{token}">'
            '<i class="fa fa-fw fa-sign-out"></i>&nbsp;&nbsp;Logout</a>'
        )
        self.assertResponseContains(
            '<script src="/static/touchtechnology/common/js/logout.js"></script>'
        )
