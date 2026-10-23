import base64
import copy
import os.path
from io import BytesIO

from django.contrib.auth.models import Permission
from django.test.utils import override_settings
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from touchtechnology.news.models import Article
from touchtechnology.news.tests.factories import ArticleFactory, TranslationFactory

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
        form = self.get_context("form")
        self.assertFormError(form, "image", "This field is required.")
        self.assertQuerySetEqual(Article.objects.all(), [])

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


class TranslationAdminTests(TestCase):
    """
    The views of an article's translations, under
    ``admin:news:article:translation``: who may use them, and that Delete
    deletes.
    """

    def setUp(self):
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.staff = UserFactory.create(is_staff=True)
        self.article = ArticleFactory.create()
        self.translation = TranslationFactory.create(article=self.article, locale="fr")
        self.kwargs = {"pk": self.article.pk, "locale": self.translation.locale}

    def assertTranslationDeleted(self):
        self.assertCountEqual(self.article.translations.all(), [])
        self.assert_http_302_found(
            url=self.reverse("admin:news:article:edit", pk=self.article.pk)
        )

    def assertTranslationKept(self):
        self.assertCountEqual(self.article.translations.all(), [self.translation])

    def test_edit_sends_an_anonymous_visitor_to_sign_in(self):
        self.assertLoginRequired("admin:news:article:translation:edit", **self.kwargs)

    def test_perms_sends_an_anonymous_visitor_to_sign_in(self):
        self.assertLoginRequired("admin:news:article:translation:perms", **self.kwargs)

    def test_delete_sends_an_anonymous_visitor_to_sign_in(self):
        self.assertLoginRequired("admin:news:article:translation:delete", **self.kwargs)
        self.assertTranslationKept()

    def test_delete_refuses_a_get(self):
        with self.login(self.superuser):
            self.get("admin:news:article:translation:delete", **self.kwargs)
        self.assert_http_405_method_not_allowed()
        self.assertTranslationKept()

    def test_superuser_deletes_the_translation(self):
        with self.login(self.superuser):
            self.post("admin:news:article:translation:delete", **self.kwargs)
        self.assertTranslationDeleted()

    def test_staff_with_the_delete_permission_deletes_the_translation(self):
        self.staff.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="news", codename="delete_translation"
            )
        )
        with self.login(self.staff):
            self.post("admin:news:article:translation:delete", **self.kwargs)
        self.assertTranslationDeleted()

    def test_staff_without_the_delete_permission_is_forbidden(self):
        with self.login(self.staff):
            self.post("admin:news:article:translation:delete", **self.kwargs)
        self.assert_http_403_forbidden()
        self.assertTranslationKept()
