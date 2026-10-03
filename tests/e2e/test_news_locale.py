"""
End-to-end validation that a news article is served at a URL carrying the
month name in the reader's own language: a Japanese reader, whose browser
sends ``Accept-Language: ja``, follows a link with the Japanese month and
gets the article, the same one the English month name serves, with its
date written in Japanese.
"""

from datetime import datetime, timezone

import pytest
from playwright.sync_api import Browser, expect
from pytest_django.live_server_helper import LiveServer

from touchtechnology.common.models import SitemapNode
from touchtechnology.content.models import Placeholder
from touchtechnology.news.tests.factories import ArticleFactory

JAPANESE_JUNE = "6月"


@pytest.fixture
def article(db):
    """
    Publish the news application at ``/news/`` with one article from the
    15th of June 2024.
    """
    placeholder, _ = Placeholder.objects.get_or_create(
        path="touchtechnology.news.sites.NewsSite", namespace="news"
    )
    SitemapNode.objects.create(title="News", slug="news", object=placeholder)

    return ArticleFactory.create(
        headline="Asia Pacific Seniors Touch Cup",
        slug="asia-pacific-seniors-touch-cup",
        abstract="Japan hosts the seniors cup in October.",
        published=datetime(2024, 6, 15, 3, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def live_server(transactional_db, settings):
    """
    A live server which chooses the language from ``Accept-Language``, as a
    site serving more than one language does.

    The test project does not enable ``LocaleMiddleware`` for every test, and
    the session's live server builds its middleware once, when it starts, so
    this module runs a server of its own with the middleware switched on.
    """
    middleware = list(settings.MIDDLEWARE)
    middleware.insert(
        middleware.index("django.contrib.sessions.middleware.SessionMiddleware") + 1,
        "django.middleware.locale.LocaleMiddleware",
    )
    settings.MIDDLEWARE = middleware

    server = LiveServer("localhost")
    yield server
    server.stop()


def _page_for(browser: Browser, locale: str):
    """A page whose browser prefers ``locale``, so sends it as ``Accept-Language``."""
    context = browser.new_context(locale=locale, ignore_https_errors=True)
    try:
        yield context.new_page()
    finally:
        context.close()


@pytest.fixture
def japanese_page(browser: Browser):
    yield from _page_for(browser, "ja-JP")


@pytest.fixture
def english_page(browser: Browser):
    yield from _page_for(browser, "en-US")


class TestNewsLocaleMonth:
    def test_article_is_served_by_japanese_month_name(
        self, japanese_page, live_server, article, screenshot_dir
    ):
        """
        Open an article, its day and its month by the Japanese name of June.

        Prerequisites:
        - The news application is published at /news/
        - One article published on 15 June 2024
        - A browser which sends ``Accept-Language: ja-JP``

        Expected behaviour:
        - The request really does carry a Japanese ``Accept-Language``
        - The article is served at ``/news/2024/6月/15/<slug>/``, with its
          date written in Japanese
        - The day and month archives for 6月 list the article
        - The English month name serves the very same article, so a
          reader following either form of the link reaches one page
        """
        page = japanese_page
        base = f"{live_server.url}/news/2024"

        response = page.goto(f"{base}/{JAPANESE_JUNE}/15/{article.slug}/")
        assert response.status == 200
        assert response.request.all_headers()["accept-language"].startswith("ja")
        expect(
            page.get_by_role("heading", level=1, name=article.headline)
        ).to_have_count(1)
        expect(page.locator("div.abstract")).to_contain_text(article.abstract)
        expect(page.locator("p.published")).to_contain_text("2024年6月15日")
        page.screenshot(path=screenshot_dir / "news_japanese_month.png")

        for path in (f"{JAPANESE_JUNE}/15/", f"{JAPANESE_JUNE}/"):
            with_month = page.goto(f"{base}/{path}")
            assert with_month.status == 200
            expect(
                page.get_by_role("link", name=article.headline).first
            ).to_be_visible()

        english = page.goto(f"{base}/jun/15/{article.slug}/")
        assert english.status == 200
        expect(
            page.get_by_role("heading", level=1, name=article.headline)
        ).to_have_count(1)

    def test_english_browser_gets_the_same_article_dated_in_english(
        self, english_page, live_server, article
    ):
        """
        The date follows the browser's language, not the month in the URL.

        Expected behaviour:
        - A browser sending ``Accept-Language: en-US`` which follows the
          Japanese month link gets the article with its date in English
        """
        english_page.goto(
            f"{live_server.url}/news/2024/{JAPANESE_JUNE}/15/{article.slug}/"
        )

        expect(english_page.locator("p.published")).to_contain_text("June 15, 2024")

    def test_unknown_month_name_is_not_found(self, japanese_page, live_server, article):
        """
        A month name in no language the site knows is a 404, not an error.

        Expected behaviour:
        - ``/news/2024/月月/15/<slug>/`` answers 404
        """
        response = japanese_page.goto(
            f"{live_server.url}/news/2024/月月/15/{article.slug}/"
        )

        assert response.status == 404
