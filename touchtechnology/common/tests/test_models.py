from django.utils.encoding import smart_str
from test_plus import TestCase
from touchtechnology.common.tests import factories


class SitemapNodeTests(TestCase):

    def setUp(self):
        self.object = factories.SitemapNodeFactory.create()

    def test_string_representation(self):
        self.assertEqual(self.object.title, smart_str(self.object))
