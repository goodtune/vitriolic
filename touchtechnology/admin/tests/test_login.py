from django.conf import settings
from test_plus import TestCase

from touchtechnology.common.tests import factories


class AdminLoginTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(
            username="admin", is_staff=True, is_superuser=True
        )

    def test_login_page_renders(self):
        self.get_check_200("admin:login")
        self.assertResponseContains("<h1>Administration</h1>", html=True)
        self.assertResponseContains('<button type="submit">Sign in</button>', html=True)

    def test_anonymous_admin_index_redirects_to_admin_login(self):
        self.get("admin:index")
        self.assertRedirects(
            self.last_response,
            f"{self.reverse('admin:login')}?next={self.reverse('admin:index')}",
            fetch_redirect_response=False,
        )

    def test_login_follows_next(self):
        target = self.reverse("admin:news:article:list")
        self.post(
            "admin:login",
            data={"username": "admin", "password": "password", "next": target},
        )
        self.response_302()
        self.assertEqual(self.last_response["Location"], target)

    def test_login_refuses_offsite_next(self):
        self.post(
            "admin:login",
            data={
                "username": "admin",
                "password": "password",
                "next": "https://example.net/",
            },
        )
        self.response_302()
        self.assertEqual(
            self.last_response["Location"], str(settings.LOGIN_REDIRECT_URL)
        )

    def test_logout_requires_post_and_lands_on_login(self):
        with self.login(self.superuser):
            self.get("admin:logout")
            self.response_405()
            self.post("admin:logout")
            self.assertRedirects(
                self.last_response,
                self.reverse("admin:login"),
                fetch_redirect_response=False,
            )
