from test_plus import TestCase
from touchtechnology.common.tests.factories import UserFactory


class AuthenticationTest(TestCase):

    def test_admin_login(self):
        self.get('admin:index')
        self.response_302()

    def test_admin_logout(self):
        user = UserFactory.create(is_staff=True)
        with self.login(user):
            self.get('accounts:logout')
            self.assertResponseContains(
                "<p>You have successfully been logged out.</p>")
