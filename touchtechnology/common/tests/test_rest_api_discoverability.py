from test_plus import TestCase


class APIDiscoverabilityTestCase(TestCase):
    def test_api_root_discoverability(self):
        """Test that /api/ root exposes available versions"""
        self.get("/api/")
        self.response_200()

        expected = {"v1": "http://testserver/api/v1/"}
        self.assertJSONEqual(self.last_response.content, expected)

    def test_api_v1_discoverability(self):
        """Test that /api/v1/ root exposes available endpoints"""
        self.get("/api/v1/")
        self.response_200()

        expected = {
            "news": "http://testserver/api/v1/news/",
            "clubs": "http://testserver/api/v1/clubs/",
            "competitions": "http://testserver/api/v1/competitions/",
        }
        self.assertJSONEqual(self.last_response.content, expected)

    def test_api_v1_news_discoverability(self):
        """Test that /api/v1/news/ shows news-specific endpoints"""
        self.get("/api/v1/news/")
        self.response_200()

        expected = {
            "categories": "http://testserver/api/v1/news/categories/",
            "articles": "http://testserver/api/v1/news/articles/",
        }
        self.assertJSONEqual(self.last_response.content, expected)
