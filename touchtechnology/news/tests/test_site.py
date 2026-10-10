import datetime

from django.db import transaction
from django.test.utils import override_settings
from django.utils import translation
from django.utils.dateformat import format as format_date
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

    def test_year_out_of_range(self):
        """
        A year datetime cannot hold is not found, and is no error to log:
        bots request such paths, ``/news/100791/jul/`` among them.
        """
        for year in (0, 100791, 10**20):
            with self.subTest(year=year):
                with self.assertNoLogs("touchtechnology.news", level="WARNING"):
                    self.get("news:month", year=year, month="jul")
                self.response_404()

    def test_last_year_datetime_can_hold(self):
        """
        In 9999 the year and day archives would query past the end of time.
        """
        with self.subTest(view="year"):
            self.get("news:year", year=9999)
            self.response_404()
        with self.subTest(view="day"):
            self.get("news:day", year=9999, month="dec", day=31)
            self.response_404()

    def test_unknown_month_name(self):
        """
        A month name the site does not know is not found, without logging an
        error. These are Django's Czech and French abbreviations for July and
        August, which links once carried when rendered in those languages.
        """
        for month in ("čec", "aoû", "月月"):
            with self.subTest(month=month):
                with self.assertNoLogs("touchtechnology.news", level="WARNING"):
                    self.get("news:month", year=2026, month=month)
                self.response_404()

    def test_day_out_of_range(self):
        with self.assertNoLogs("touchtechnology.news", level="WARNING"):
            self.get("news:day", year=2026, month="jul", day=32)
        self.response_404()


@override_settings(ROOT_URLCONF="example_app.urls")
class LocaleIndependentLinkTest(TestCase):
    """
    Links to articles and archives spell the month in English whichever
    language is active, so they do not depend on the reader's language.
    """

    def test_day_archive(self):
        article = factories.ArticleFactory.create(
            published=datetime.datetime(2013, 7, 23, 3, 0, tzinfo=datetime.timezone.utc)
        )
        with translation.override("cs"):
            self.assertGoodView("news:day", year=2013, month="jul", day=23)
        self.assertResponseContains(
            f'<a href="/news/2013/jul/23/{article.slug}/">{article.headline}</a>'
        )

    def test_year_archive(self):
        published = datetime.datetime(2013, 7, 23, 3, 0, tzinfo=datetime.timezone.utc)
        factories.ArticleFactory.create(published=published)
        with translation.override("cs"):
            self.assertGoodView("news:year", year=2013)
            title = format_date(published, "F Y")
        self.assertResponseContains(f'<a href="/news/2013/jul/">{title}</a>')

    def test_article_list(self):
        article = factories.ArticleFactory.create(
            published=datetime.datetime(2013, 8, 23, 3, 0, tzinfo=datetime.timezone.utc)
        )
        with translation.override("fr"):
            self.assertGoodView("news:index")
            read_more = translation.gettext("Read more")
        self.assertResponseContains(
            f'<a class="button more" href="/news/2013/aug/23/{article.slug}/">'
            f"{read_more}</a>"
        )

    def test_related_articles(self):
        published = datetime.datetime(2013, 10, 23, 3, 0, tzinfo=datetime.timezone.utc)
        category = factories.CategoryFactory.create()
        article, related = factories.ArticleFactory.create_batch(2, published=published)
        article.categories.set([category])
        related.categories.set([category])
        with translation.override("ja"):
            self.assertGoodView(
                "news:article",
                year=2013,
                month="oct",
                day=23,
                slug=article.slug,
            )
        self.assertResponseContains(
            f'<a href="/news/2013/oct/23/{related.slug}/">{related.headline}</a>'
        )


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
            **kwargs,
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
