import base64
import copy
import os.path

from django.test.utils import override_settings
from test_plus import TestCase
from touchtechnology.common.tests.factories import UserFactory
from touchtechnology.news.models import Article

try:
    from io import BytesIO
except ImportError:
    from StringIO import StringIO as BytesIO


TEST_DIR = os.path.join(os.path.dirname(__file__), 'html')


class ImageFieldTestCase(TestCase):

    def setUp(self):
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

        # Single transparent pixel PNG image, base64 encoded.
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkkAAAACklEQVQImWNoAAAA"
            "ggCByxOyYQAAAABJRU5ErkJggg==")

        self.data_no_image = {
            'form-headline': 'Headline',
            'form-image': None,
            'form-abstract': 'This is the abstract',
            'form-published': '2017-01-01 05:30:00',
            'formset-0-copy': '',
            'formset-0-label': 'copy',
            'formset-0-sequence': '1',
            'formset-TOTAL_FORMS': '1',
            'formset-INITIAL_FORMS': '0',
            'formset-MIN_NUM_FORMS': '0',
            'formset-MAX_NUM_FORMS': '100',
        }
        self.data_with_image = copy.copy(self.data_no_image)
        self.data_with_image['form-image'] = BytesIO(png_data)
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
