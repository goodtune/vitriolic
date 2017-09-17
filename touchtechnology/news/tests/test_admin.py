import base64
import copy
import os.path
import StringIO

from dateutil.parser import parse as parse_datetime
from django.test.utils import override_settings
from django.utils import timezone
from test_plus import TestCase
from touchtechnology.common.tests.factories import UserFactory
from touchtechnology.news.models import Article
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


class ImageFieldTestCase(TestCase):

    def setUp(self):
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.data_no_image = {
            'form-headline': 'Headline',
            'form-image': None,
            'form-abstract': 'This is the abstract',
            'form-published_0': '1',
            'form-published_1': '1',
            'form-published_2': '2017',
            'form-published_3': '5',
            'form-published_4': '30',
            'form-published_5': 'Asia/Kabul',
            'formset-0-copy': '',
            'formset-0-label': 'copy',
            'formset-0-sequence': '1',
            'formset-TOTAL_FORMS': '1',
            'formset-INITIAL_FORMS': '0',
            'formset-MIN_NUM_FORMS': '0',
            'formset-MAX_NUM_FORMS': '100',
        }
        self.data_with_image = copy.copy(self.data_no_image)
        self.data_with_image['form-image'] = StringIO.StringIO(
            # Single transparent pixel PNG image, base64 encoded.
            base64.decodestring("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkk"
                                "AAAACklEQVQImWNoAAAAggCByxOyYQAAAABJRU5ErkJg"
                                "gg=="))
        # From Django 1.11 the image field validates the filename.
        self.data_with_image['form-image'].name = 'pixel.png'

    def test_image_required_no_image(self):
        with self.login(self.superuser):
            self.post('admin:news:article:add', data=self.data_no_image)
        self.assertFormError(
            self.last_response, 'form', 'image', 'This field is required.')
        self.assertEqual(0, Article.objects.count())

    def test_image_required_with_image(self):
        with self.login(self.superuser):
            self.post('admin:news:article:add', data=self.data_with_image)
        self.response_302()
        self.assertEqual(1, Article.objects.count())

    @override_settings(TOUCHTECHNOLOGY_NEWS_IMAGE_REQUIRED=False)
    def test_image_not_required_no_image(self):
        with self.login(self.superuser):
            self.post('admin:news:article:add', data=self.data_no_image)
        self.response_302()
        self.assertEqual(1, Article.objects.count())

    @override_settings(TOUCHTECHNOLOGY_NEWS_IMAGE_REQUIRED=False)
    def test_image_not_required_with_image(self):
        with self.login(self.superuser):
            self.post('admin:news:article:add', data=self.data_with_image)
        self.response_302()
        self.assertEqual(1, Article.objects.count())
