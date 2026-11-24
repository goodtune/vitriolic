"""
Paths that only need to know whether rows exist ask with ``exists()``, never
with a ``COUNT(*)`` (#581).
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from test_plus import TestCase

from touchtechnology.common.models import SitemapNode
from touchtechnology.content.forms import SitemapNodeForm
from touchtechnology.content.models import Placeholder


class ExistsNotCountTests(TestCase):
    def assertNoCount(self, func, *args, **kwargs):
        with CaptureQueriesContext(connection) as queries:
            func(*args, **kwargs)
        self.assertEqual(
            [query["sql"] for query in queries if "COUNT(" in query["sql"]], []
        )

    def test_sitemap_node_form_without_groups(self):
        self.assertNoCount(SitemapNodeForm)
        self.assertNotIn("restrict_to_groups", SitemapNodeForm().fields)

    def test_placeholder_install_when_already_installed(self):
        placeholder = Placeholder.objects.create(
            path="touchtechnology.news.sites.NewsSite", namespace="news"
        )
        node = SitemapNode.objects.create(title="News", object=placeholder)
        self.assertNoCount(placeholder._install)
        self.assertCountEqual(placeholder.nodes.all(), [node])
