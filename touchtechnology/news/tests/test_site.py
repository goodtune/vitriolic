import factory
from django.db import transaction
from django.test.utils import override_settings
from test_plus import TestCase
from touchtechnology.news.tests import factories


@override_settings(ROOT_URLCONF="example_app.urls")
class InvalidDateTest(TestCase):
    def test_archive_day(self):
        self.get("news:article", year="2013", month="feb", day="31")
        self.response_404()

    def test_article(self):
        self.get(
            "news:article",
            year="2013",
            month="feb",
            day="31",
            slug="tfms-new-generaltechnical-manager",
        )
        self.response_404()


@override_settings(ROOT_URLCONF="example_app.urls")
class FeedTest(TestCase):
    def test_atom(self):
        self.assertGoodView("news:feed-atom")

    def test_rss(self):
        self.assertGoodView("news:feed-rss")


@override_settings(ROOT_URLCONF="example_app.urls")
class SiteTest(TestCase):
    def assertGoodArticleView(self, article, **kwargs):
        self.assertGoodView(
            "news:article",
            year=article.published.year,
            month=article.published.strftime("%b").lower(),
            day=article.published.day,
            slug=article.slug,
            **kwargs
        )

    def test_article(self):
        article = factories.ArticleFactory.create(
            headline="This is a predictable headline!"
        )
        self.assertEqual(article.slug, "this-is-a-predictable-headline")
        self.assertGoodArticleView(article)

    def test_article_one_category(self):
        categories = factories.CategoryFactory.create_batch(1)
        article = factories.ArticleFactory.create()
        article.categories.set(categories)
        self.assertGoodArticleView(article)

    def test_article_many_categories(self):
        categories = factories.CategoryFactory.create_batch(3)
        article = factories.ArticleFactory.create()
        article.categories.set(categories)
        self.assertGoodArticleView(article)

    def test_multiple_articles_related_categories(self):
        with transaction.atomic():
            categories = factories.CategoryFactory.create_batch(3)
            articles = factories.ArticleFactory.create_batch(2)
            for article in articles:
                article.categories.set(categories)
        self.assertGoodArticleView(article)

    def test_article_translation(self):
        article = factories.ArticleFactory.create(headline="This is in English")
        translation = factories.TranslationFactory.create(
            locale="de", article_id=article.pk, headline="Das ist in Deutsch"
        )
        with self.subTest(msg="Article references Translation"):
            self.assertGoodArticleView(article)
            self.assertResponseContains(
                '<a class="de" href="{}">Deutsch (German)</a>'.format(
                    translation.get_absolute_url()
                )
            )
        with self.subTest(msg="Translation references Article"):
            self.assertGoodView(
                "news:translation",
                year=article.published.year,
                month=article.published.strftime("%b").lower(),
                day=article.published.day,
                slug=article.slug,
                locale="de",
            )
            self.assertResponseContains(
                '<a href="{}">This is in English</a>'.format(article.get_absolute_url())
            )
