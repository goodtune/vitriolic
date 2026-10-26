import importlib
import sys

from django.conf import settings
from django.urls import clear_url_caches
from test_plus import TestCase

# The v1 URLconf decides which apps' routes it includes when it is imported,
# so a change to INSTALLED_APPS only reaches it once the module is executed
# again. Each resolver that includes it keeps the pattern list it first read,
# so every module from the v1 URLconf up to the root is reloaded, innermost
# first. Parallel test workers start without any of them imported, and the
# first request in a worker may be made by a test that has removed an app.
API_URLCONFS = (
    "touchtechnology.common.rest.v1.urls",
    "touchtechnology.common.rest.urls",
)


def rebuild_api_urlconf():
    for name in API_URLCONFS + (settings.ROOT_URLCONF,):
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    clear_url_caches()


class OptionalAppsAPITestCase(TestCase):
    def without_news(self):
        """
        Remove the news app and rebuild the API URLconf without it. Both are
        undone, in that order, when the test ends.
        """
        context = self.modify_settings(
            INSTALLED_APPS={"remove": ["touchtechnology.news"]}
        )
        context.enable()
        self.addCleanup(rebuild_api_urlconf)
        self.addCleanup(context.disable)
        rebuild_api_urlconf()

    def test_api_works_without_news_app(self):
        """Test that the API entrypoint works when news app is not installed"""
        self.without_news()
        self.get("/api/")
        self.response_200()

        # Should show only v1 endpoint
        expected = {"v1": "http://testserver/api/v1/"}
        self.assertJSONEqual(self.last_response.content, expected)

    def test_v1_api_adapts_to_installed_apps(self):
        """Test that v1 API only shows endpoints for installed apps"""
        self.without_news()
        self.get("/api/v1/")
        self.response_200()

        # Should show only competition endpoints, no news
        expected = {
            "clubs": "http://testserver/api/v1/clubs/",
            "competitions": "http://testserver/api/v1/competitions/",
        }
        self.assertJSONEqual(self.last_response.content, expected)

    def test_v1_api_shows_all_endpoints_when_all_apps_installed(self):
        """Test that v1 API shows all endpoints when all apps are installed"""
        self.get("/api/v1/")
        self.response_200()

        # Should show all available endpoints
        expected = {
            "news": "http://testserver/api/v1/news/",
            "clubs": "http://testserver/api/v1/clubs/",
            "competitions": "http://testserver/api/v1/competitions/",
        }
        self.assertJSONEqual(self.last_response.content, expected)
