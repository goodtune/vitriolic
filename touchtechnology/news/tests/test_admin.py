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


TEST_DIR = os.path.join(os.path.dirname(__file__), "html")


class ImageFieldTestCase(TestCase):
    def setUp(self):
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

        # Single transparent pixel PNG image, base64 encoded.
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkkAAAACklEQVQImWNoAAAA"
            "ggCByxOyYQAAAABJRU5ErkJggg=="
        )

        self.data_no_image = {
            "headline": "Headline",
            "image": "",
            "abstract": "This is the abstract",
            "copy": "<p>This is the copy</p>",
            "published": "2017-01-01 05:30:00",
        }
        self.data_with_image = copy.copy(self.data_no_image)
        self.data_with_image["image"] = BytesIO(png_data)
        self.data_with_image["image"].name = "pixel.png"

    def test_image_required_no_image(self):
        with self.login(self.superuser):
            self.post("admin:news:article:add", data=self.data_no_image)
        self.assertFormError(
            self.last_response, "form", "image", "This field is required."
        )
        self.assertEqual(0, Article.objects.count())

    def test_image_required_with_image(self):
        with self.login(self.superuser):
            self.post("admin:news:article:add", data=self.data_with_image)
        # print(self.last_response.content.decode("utf-8"))
        self.response_302()
        self.assertEqual(1, Article.objects.count())

    @override_settings(TOUCHTECHNOLOGY_NEWS_IMAGE_REQUIRED=False)
    def test_image_not_required_no_image(self):
        with self.login(self.superuser):
            self.post("admin:news:article:add", data=self.data_no_image)
        # print(self.last_response.content.decode("utf-8"))
        self.response_302()
        self.assertEqual(1, Article.objects.count())

    @override_settings(TOUCHTECHNOLOGY_NEWS_IMAGE_REQUIRED=False)
    def test_image_not_required_with_image(self):
        with self.login(self.superuser):
            self.post("admin:news:article:add", data=self.data_with_image)
        # print(self.last_response.content.decode("utf-8"))
        self.response_302()
        self.assertEqual(1, Article.objects.count())
