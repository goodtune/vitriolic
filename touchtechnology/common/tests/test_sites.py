from django.test.utils import override_settings
from test_plus import TestCase

from touchtechnology.common.sites import AccountsSite


@override_settings(ROOT_URLCONF="example_app.urls")
class ApplicationTests(TestCase):
    def test_reverse(self):
        self.assertEqual(
            str(AccountsSite().reverse("login")), self.reverse("accounts:login")
        )
