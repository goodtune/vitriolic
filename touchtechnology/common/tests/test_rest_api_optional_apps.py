from django.test import modify_settings
from test_plus import TestCase


class OptionalAppsAPITestCase(TestCase):
    @modify_settings(INSTALLED_APPS={"remove": ["touchtechnology.news"]})
    def test_api_works_without_news_app(self):
        """Test that the API entrypoint works when news app is not installed"""
        self.get("/api/")
        self.response_200()

        # Should show only v1 endpoint
        expected = {"v1": "http://testserver/api/v1/"}
        self.assertJSONEqual(self.last_response.content, expected)

    @modify_settings(INSTALLED_APPS={"remove": ["touchtechnology.news"]})
    def test_v1_api_adapts_to_installed_apps(self):
        """Test that v1 API only shows endpoints for installed apps"""
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
