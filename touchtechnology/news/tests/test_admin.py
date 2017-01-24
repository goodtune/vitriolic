import os.path
import re

from dateutil.parser import parse as parse_datetime
from django.test.utils import modify_settings, override_settings
from django.utils import timezone
from test_plus import TestCase
from touchtechnology.common.tests.factories import UserFactory
from touchtechnology.news.tests.factories import ArticleFactory

TEST_DIR = os.path.join(os.path.dirname(__file__), 'html')


def get_html_fragment(filename):
    with open(os.path.join(TEST_DIR, filename)) as fp:
        html = fp.read()
    return html


class PublishedTimeZoneTestCase(TestCase):

    def setUp(self):
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.article = ArticleFactory.create(
            published=parse_datetime('2013-1-1 12:00+00:00'))

    def test_published_datetime_html(self):
        self.assertLoginRequired('admin:news:article:edit', self.article.pk)
        with self.login(self.superuser):
            self.get('admin:news:article:edit', self.article.pk)
            for i in range(5):
                html = get_html_fragment(
                    'select_date_time_published_%d.html' % i)
                self.assertInHTML(html, self.last_response.content, count=1)

    def test_published_datetime_html_tz(self):
        with timezone.override('Australia/Sydney'):
            with self.login(self.superuser):
                self.get('admin:news:article:edit', self.article.pk)
                html = get_html_fragment(
                    'select_date_time_published_3-Sydney.html')
                self.assertInHTML(html, self.last_response.content, count=1)
