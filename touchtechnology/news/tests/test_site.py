from test_plus import TestCase
from django.test.utils import override_settings


@override_settings(ROOT_URLCONF='example_app.urls')
class InvalidDateTest(TestCase):

    def test_archive_day(self):
        self.get('news:article', year='2013', month='feb', day='31')
        self.response_404()

    def test_article(self):
        self.get('news:article', year='2013', month='feb', day='31',
                 slug='tfms-new-generaltechnical-manager')
        self.response_404()


@override_settings(ROOT_URLCONF='example_app.urls')
class FeedTest(TestCase):

    def test_atom(self):
        self.assertGoodView('news:feed', format='atom')

    def test_rss(self):
        self.assertGoodView('news:feed', format='rss')
