"""
Paths that only need to know whether rows exist ask with ``exists()``, never
with a ``COUNT(*)`` (#581).
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from test_plus import TestCase

from touchtechnology.news.forms import ArticleForm


class ExistsNotCountTests(TestCase):
    def test_article_form_without_categories(self):
        with CaptureQueriesContext(connection) as queries:
            form = ArticleForm()
        self.assertEqual(
            [query["sql"] for query in queries if "COUNT(" in query["sql"]], []
        )
        self.assertNotIn("categories", form.fields)
