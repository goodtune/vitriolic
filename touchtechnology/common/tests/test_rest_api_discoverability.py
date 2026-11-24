from test_plus import TestCase


class APIDiscoverabilityTestCase(TestCase):
    def test_api_root_discoverability(self):
        """Test that /api/ root exposes available versions"""
        self.get_check_200("api-root")

        expected = {"v1": "http://testserver/api/v1/"}
        self.assertJSONEqual(self.last_response.content, expected)

    def test_api_v1_discoverability(self):
        """Test that /api/v1/ root exposes available endpoints"""
        self.get_check_200("v1:api-root")

        expected = {
            "news": "http://testserver/api/v1/news/",
            "clubs": "http://testserver/api/v1/clubs/",
            "competitions": "http://testserver/api/v1/competitions/",
        }
        self.assertJSONEqual(self.last_response.content, expected)

    def test_api_v1_news_discoverability(self):
        """Test that /api/v1/news/ shows news-specific endpoints"""
        self.get_check_200("v1:news:api-root")

        expected = {
            "categories": "http://testserver/api/v1/news/categories/",
            "articles": "http://testserver/api/v1/news/articles/",
        }
        self.assertJSONEqual(self.last_response.content, expected)
