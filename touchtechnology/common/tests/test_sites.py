import django
from django.test.utils import override_settings
from test_plus import TestCase

from touchtechnology.common.sites import AccountsSite


class VersionedSite(AccountsSite):
    """A site whose package, two levels up, has a ``__version__``."""

    __module__ = "django.contrib.sites"


@override_settings(ROOT_URLCONF="example_app.urls")
class ApplicationTests(TestCase):
    def test_version_from_the_package(self):
        self.assertEqual(VersionedSite().version, f"Accounts {django.__version__}")

    def test_version_without_one(self):
        self.assertEqual(AccountsSite().version, "Accounts ")

    def test_reverse(self):
        self.assertEqual(
            str(AccountsSite().reverse("login")), self.reverse("accounts:login")
        )
