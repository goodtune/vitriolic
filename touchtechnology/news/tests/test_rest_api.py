from rest_framework.test import APIClient
from test_plus import TestCase

from touchtechnology.news.tests.factories import (
    ArticleFactory,
    CategoryFactory,
)


class NewsAPITestCase(TestCase):
    client_class = APIClient

    def setUp(self):
        super().setUp()
        self.category = CategoryFactory()
        self.article = ArticleFactory()
        self.article.categories.add(self.category)

    def test_categories_list_endpoint(self):
        """Test that categories list endpoint returns active categories."""
        self.get("v1:news:category-list")
        self.assert_http_200_ok()
        data = self.last_response.data
        # Check if it's a paginated response or direct list
        if isinstance(data, dict) and "results" in data:
            data = data["results"]
        self.assertEqual([cat["slug"] for cat in data], [self.category.slug])

    def test_categories_detail_endpoint(self):
        """Test that category detail endpoint returns category data."""
        self.get("v1:news:category-detail", slug=self.category.slug)
        self.assert_http_200_ok()
        self.assertEqual(self.last_response.data["slug"], self.category.slug)
        self.assertEqual(self.last_response.data["title"], self.category.title)

    def test_articles_list_endpoint(self):
        """Test that articles list endpoint returns active articles."""
        self.get("v1:news:article-list")
        self.assert_http_200_ok()
        # Direct list response (not paginated)
        self.assertEqual(
            [art["slug"] for art in self.last_response.data], [self.article.slug]
        )

    def test_articles_detail_endpoint(self):
        """Test that article detail endpoint returns article data with copy content."""
        self.get("v1:news:article-detail", slug=self.article.slug)
        self.assert_http_200_ok()
        self.assertEqual(self.last_response.data["slug"], self.article.slug)
        self.assertEqual(self.last_response.data["headline"], self.article.headline)
        self.assertIn("copy", self.last_response.data)
        self.assertIn("keywords", self.last_response.data)

    def test_inactive_categories_excluded(self):
        """Test that inactive categories are excluded from API responses."""
        CategoryFactory(is_active=False)
        self.get("v1:news:category-list")
        self.assert_http_200_ok()
        self.assertCountEqual(
            [cat["slug"] for cat in self.last_response.data], [self.category.slug]
        )

    def test_inactive_articles_excluded(self):
        """Test that inactive articles are excluded from API responses."""
        ArticleFactory(is_active=False)
        self.get("v1:news:article-list")
        self.assert_http_200_ok()
        self.assertCountEqual(
            [art["slug"] for art in self.last_response.data], [self.article.slug]
        )
