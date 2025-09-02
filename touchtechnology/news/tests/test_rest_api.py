from django.urls import reverse
from rest_framework.test import APIClient
from test_plus import TestCase

from touchtechnology.news.tests.factories import (
    ArticleFactory,
    CategoryFactory,
)


class NewsAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = CategoryFactory()
        self.article = ArticleFactory()
        self.article.categories.add(self.category)

    def test_categories_list_endpoint(self):
        """Test that categories list endpoint returns active categories."""
        url = reverse("v1:news:category-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Check if it's a paginated response or direct list
        if isinstance(response.data, dict) and "results" in response.data:
            # Paginated response
            self.assertEqual(len(response.data["results"]), 1)
            self.assertEqual(response.data["results"][0]["slug"], self.category.slug)
        else:
            # Direct list response
            self.assertEqual(len(response.data), 1)
            self.assertEqual(response.data[0]["slug"], self.category.slug)

    def test_categories_detail_endpoint(self):
        """Test that category detail endpoint returns category data."""
        url = reverse("v1:news:category-detail", kwargs={"slug": self.category.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["slug"], self.category.slug)
        self.assertEqual(response.data["title"], self.category.title)

    def test_articles_list_endpoint(self):
        """Test that articles list endpoint returns active articles."""
        url = reverse("v1:news:article-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Direct list response (not paginated)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["slug"], self.article.slug)

    def test_articles_detail_endpoint(self):
        """Test that article detail endpoint returns article data with copy content."""
        url = reverse("v1:news:article-detail", kwargs={"slug": self.article.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["slug"], self.article.slug)
        self.assertEqual(response.data["headline"], self.article.headline)
        self.assertIn("copy", response.data)
        self.assertIn("keywords", response.data)

    def test_inactive_categories_excluded(self):
        """Test that inactive categories are excluded from API responses."""
        inactive_category = CategoryFactory(is_active=False)
        url = reverse("v1:news:category-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        slugs = [cat["slug"] for cat in response.data]
        self.assertNotIn(inactive_category.slug, slugs)

    def test_inactive_articles_excluded(self):
        """Test that inactive articles are excluded from API responses."""
        inactive_article = ArticleFactory(is_active=False)
        url = reverse("v1:news:article-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        slugs = [art["slug"] for art in response.data]
        self.assertNotIn(inactive_article.slug, slugs)
