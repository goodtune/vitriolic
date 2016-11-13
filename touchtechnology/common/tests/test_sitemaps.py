from test_plus import TestCase


class SitemapsTest(TestCase):

    def test_sitemap_xml(self):
        self.assertGoodView('sitemap')
