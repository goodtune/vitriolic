import base64
import copy
import os.path
from io import BytesIO

from django.contrib.auth.models import Permission
from django.test.utils import override_settings
from guardian.shortcuts import assign_perm
from test_plus import TestCase

from touchtechnology.admin.tests.lists import unordered_pages_fail
from touchtechnology.admin.tests.shells import IconMixin, per_shell
from touchtechnology.common.tests.factories import (
    StaffFactory,
    SuperUserFactory,
    UserFactory,
)
from touchtechnology.news.models import Article
from touchtechnology.news.tests.factories import (
    ArticleFactory,
    CategoryFactory,
    TranslationFactory,
)

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


@per_shell
@override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
class TranslationsTabTests(TestCase):
    """
    An article's Translations tab, fetched on its own as the page fetches it
    when the tab is first shown: a page of the article's translations.
    """

    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        cls.superuser = cls.make_user("superuser")
        cls.article = ArticleFactory.create()

    def get_tab(self):
        with self.login(self.superuser):
            self.get(
                "admin:news:article:edit",
                pk=self.article.pk,
                data={"_htmx_tab": "translations"},
                extra={"HTTP_HX_REQUEST": "true"},
            )
        self.assert_http_200_ok()

    def test_the_tab_lists_the_translations_by_locale(self):
        french = TranslationFactory.create(article=self.article, locale="fr")
        german = TranslationFactory.create(article=self.article, locale="de")
        italian = TranslationFactory.create(article=self.article, locale="it")
        with unordered_pages_fail():
            self.get_tab()
        self.assertEqual(
            list(self.get_context("object_list")), [german, french, italian]
        )

    def test_an_article_with_no_translations_says_so(self):
        self.get_tab()
        add = self.reverse("admin:news:article:translation:add", pk=self.article.pk)
        self.assertResponseContains(
            self.by_shell(
                workbook=(
                    '<tr class="wb-table-empty"><td colspan="3">'
                    f'No translations yet. <a href="{add}">Add the first translation</a>'
                    "</td></tr>"
                ),
                explorer=(
                    '<tr><td colspan="3" class="empty-state">'
                    f'No translations yet. <a href="{add}">Add the first translation</a>.'
                    "</td></tr>"
                ),
            )
        )


@override_settings(TOUCHTECHNOLOGY_NEWS_IMAGE_REQUIRED=False)
class ArticleEditPermissionTests(TestCase):
    """
    Who may open and save an article's edit page: staff need
    ``news.change_article`` on the article or globally.
    """

    user_factory = StaffFactory

    @classmethod
    def setUpTestData(cls):
        cls.article = ArticleFactory.create(headline="Before")
        cls.other_article = ArticleFactory.create()
        cls.data = {
            "headline": "After",
            "abstract": "This is the abstract",
            "copy": "<p>This is the copy</p>",
            "published": "2017-01-01 05:30:00",
            "is_active": "1",
        }

    def assertArticleSaved(self):
        self.assert_http_302_found(url=self.reverse("admin:news:article:list"))
        self.article.refresh_from_db()
        self.assertEqual(self.article.headline, "After")

    def assertArticleUnchanged(self):
        self.article.refresh_from_db()
        self.assertEqual(self.article.headline, "Before")

    def test_edit_sends_an_anonymous_visitor_to_sign_in(self):
        self.assertLoginRequired("admin:news:article:edit", pk=self.article.pk)

    def test_staff_without_the_change_permission_cannot_open_the_page(self):
        staff = self.make_user("staff")
        with self.login(staff):
            self.get("admin:news:article:edit", pk=self.article.pk)
        self.assert_http_403_forbidden()

    def test_staff_without_the_change_permission_cannot_save(self):
        staff = self.make_user("staff")
        with self.login(staff):
            self.post("admin:news:article:edit", pk=self.article.pk, data=self.data)
        self.assert_http_403_forbidden()
        self.assertArticleUnchanged()

    def test_permission_on_another_article_does_not_open_this_one(self):
        staff = self.make_user("staff")
        assign_perm("news.change_article", staff, self.other_article)
        with self.login(staff):
            self.get("admin:news:article:edit", pk=self.article.pk)
        self.assert_http_403_forbidden()

    def test_staff_with_the_object_permission_opens_and_saves(self):
        staff = self.make_user("staff")
        assign_perm("news.change_article", staff, self.article)
        with self.login(staff):
            self.get_check_200("admin:news:article:edit", pk=self.article.pk)
            self.post("admin:news:article:edit", pk=self.article.pk, data=self.data)
        self.assertArticleSaved()

    def test_staff_with_the_global_permission_opens_and_saves(self):
        staff = self.make_user("staff")
        assign_perm("news.change_article", staff)
        with self.login(staff):
            self.get_check_200("admin:news:article:edit", pk=self.article.pk)
            self.post("admin:news:article:edit", pk=self.article.pk, data=self.data)
        self.assertArticleSaved()


@per_shell
class CategoryListTests(TestCase):
    """The list of categories, shown a page at a time."""

    user_factory = SuperUserFactory

    def test_the_categories_are_listed_by_title(self):
        superuser = self.make_user("superuser")
        sport = CategoryFactory.create(title="Sport")
        club = CategoryFactory.create(title="Club news")
        events = CategoryFactory.create(title="Events")
        with unordered_pages_fail(), self.login(superuser):
            self.get("admin:news:category:list")
        self.assert_http_200_ok()
        self.assertEqual(list(self.get_context("object_list")), [club, events, sport])


@per_shell
class ArticleListPermissionTests(IconMixin, TestCase):
    """
    The list of articles offers Edit to whoever may change the article:
    ``change_article`` on the article, or on every article, which is what the
    article's own page and its delete view accept.
    """

    user_factory = StaffFactory

    def setUp(self):
        super().setUp()
        self.staff = self.make_user("staff")
        self.article = ArticleFactory.create(headline="Grand final preview")

    def edit_item(self):
        """The Edit item of the article's row menu."""
        url = self.reverse("admin:news:article:edit", self.article.pk)
        return self.by_shell(
            workbook=f'<li><a href="{url}">{self.icon("pencil")}Edit</a></li>',
            explorer=f'<a href="{url}">{self.icon("edit")}Edit</a>',
        )

    def test_change_article_on_every_article_offers_edit(self):
        assign_perm("news.change_article", self.staff)
        with self.login(self.staff):
            self.get_check_200("admin:news:article:list")
        self.assertResponseContains(self.edit_item())

    def test_change_article_on_the_article_offers_edit(self):
        assign_perm("news.change_article", self.staff, self.article)
        with self.login(self.staff):
            self.get_check_200("admin:news:article:list")
        self.assertResponseContains(self.edit_item())

    def test_delete_article_alone_withholds_edit(self):
        assign_perm("news.delete_article", self.staff, self.article)
        with self.login(self.staff):
            self.get_check_200("admin:news:article:list")
        self.assertResponseContains(self.edit_item(), count=0)
