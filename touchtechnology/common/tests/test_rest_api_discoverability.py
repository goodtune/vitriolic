from test_plus import TestCase


class APIDiscoverabilityTestCase(TestCase):
    def test_api_root_discoverability(self):
        """Test that /api/ root exposes available versions"""
        response = self.get("/api/")
        self.response_200()
        
        # Should show v1 is available
        data = response.json()
        self.assertIn("v1", data)
        
    def test_api_v1_discoverability(self):
        """Test that /api/v1/ root exposes available endpoints"""
        response = self.get("/api/v1/")
        self.response_200()
        
        data = response.json()
        # Should show both news and competition endpoints
        self.assertIn("news", data)
        # Competition endpoints should be exposed at root level
        self.assertIn("clubs", data)
        self.assertIn("competitions", data)
        
    def test_api_v1_news_discoverability(self):
        """Test that /api/v1/news/ shows news-specific endpoints"""
        response = self.get("/api/v1/news/")
        self.response_200()
        
        data = response.json()
        self.assertIn("categories", data)
        self.assertIn("articles", data)