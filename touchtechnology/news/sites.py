from __future__ import unicode_literals

from dateutil.relativedelta import relativedelta
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from django.utils.feedgenerator import Atom1Feed
from touchtechnology.common.sites import Application
from touchtechnology.news.app_settings import PAGINATE_BY
from touchtechnology.news.decorators import (
    date_view, last_modified_article, news_last_modified,
)
from touchtechnology.news.models import Article, Category, Translation
from touchtechnology.news.syndication import ExtendedRSSFeed, NewsFeed

YEAR_DELTA = relativedelta(years=1)
MONTH_DELTA = relativedelta(months=1)
DAY_DELTA = relativedelta(days=1)


class NewsSite(Application):
    def __init__(self, name="news", app_name="news", **kwargs):
        self.node = kwargs.get("node")  # store the node for future reference
        super().__init__(name=name, app_name=app_name, **kwargs)

    def get_urls(self):
        return [
            path("", self.index, name="index",),
            path("<int:year>/", self.archive_year, name="year"),
            path("<int:year>/<str:month>/", self.archive_month, name="month",),
            path("<int:year>/<str:month>/<int:day>/", self.archive_day, name="day",),
            path(
                "<int:year>/<str:month>/<int:day>/<slug:slug>/",
                self.article,
                name="article",
            ),
            path(
                "<int:year>/<str:month>/<int:day>/<slug:slug>/<str:locale>/",
                self.translation,
                name="translation",
            ),
            path("feeds/", self.feeds, name="feeds"),
            path("feeds/atom/", self.feed, kwargs={"format": "atom"}, name="feed-atom"),
            path("feeds/rss/", self.feed, kwargs={"format": "rss"}, name="feed-rss"),
            path("archive/", self.archive, name="archive"),
            path("<str:category>/", self.list_articles, name="category"),
        ]

    @property
    def urls(self):
        return self.get_urls(), self.app_name, self.name

    @property
    def categories(self):
        return Category.objects.all()

    @news_last_modified
    def index(self, request, **extra_context):
        return self.generic_list(
            request,
            Article.objects.live()[:PAGINATE_BY],
            templates=self.template_path("index.html"),
            extra_context=extra_context,
        )

    @news_last_modified
    def list_articles(self, request, **extra_context):
        queryset = Article.objects.live()
        category = extra_context.get("category")
        if category is not None:
            queryset = queryset.filter(categories__slug=category)
        return self.generic_list(
            request, Article, queryset=queryset, extra_context=extra_context,
        )

    @date_view
    @last_modified_article
    def article(self, request, date, slug, **extra_context):
        return self.generic_detail(
            request,
            Article.objects.live(),
            published__range=(date, date + DAY_DELTA),
            slug=slug,
            extra_context=extra_context,
        )

    @date_view
    @last_modified_article
    def translation(self, request, date, slug, locale, **extra_context):
        article = get_object_or_404(
            Article.objects.live(),
            published__range=(date, date + DAY_DELTA),
            slug=slug,
        )
        return self.generic_detail(
            request, article.translations, locale=locale, extra_context=extra_context,
        )

    @date_view
    @last_modified_article
    def archive_day(self, request, date, **kwargs):
        queryset = Article.objects.live().filter(
            published__range=(date, date + DAY_DELTA)
        )
        context = {
            "day": date,
            "object_list": queryset,
        }
        context.update(kwargs)
        templates = ["touchtechnology/news/archive/day.html"]
        return self.render(request, templates, context)

    @date_view
    @last_modified_article
    def archive_month(self, request, date, **kwargs):
        queryset = Article.objects.live().filter(
            published__range=(date, date + MONTH_DELTA)
        )
        try:
            date_list = queryset.datetimes("published", "day", tzinfo=timezone.utc)
        except AttributeError:
            date_list = queryset.dates("published", "day")
        context = {
            "date_list": date_list,
            "month": date,
            "object_list": queryset,
        }
        context.update(kwargs)
        templates = ["touchtechnology/news/archive/month.html"]
        return self.render(request, templates, context)

    @date_view
    @last_modified_article
    def archive_year(self, request, date, **kwargs):
        queryset = Article.objects.live().filter(
            published__range=(date, date + YEAR_DELTA)
        )
        try:
            date_list = queryset.datetimes("published", "month", tzinfo=timezone.utc)
        except AttributeError:
            date_list = queryset.dates("published", "month")

        # compatibility with date_based.archive_year
        year = str(date.year)

        context = {
            "date_list": date_list,
            "year": year,
            "object_list": queryset,
        }
        context.update(kwargs)

        templates = ["touchtechnology/news/archive/year.html"]
        return self.render(request, templates, context)

    def archive(self, request, **kwargs):
        queryset = Article.objects.live()
        try:
            date_list = queryset.datetimes("published", "year", tzinfo=timezone.utc)
        except AttributeError:
            date_list = queryset.dates("published", "year")
        context = {
            "date_list": date_list,
            "latest": queryset.order_by("-published")[:15],
        }
        context.update(kwargs)
        templates = ["touchtechnology/news/archive/index.html"]
        return self.render(request, templates, context)

    def feeds(self, request, **kwargs):
        context = {
            "feeds": {"ATOM": "atom", "RSS": "rss",},
        }
        context.update(kwargs)
        templates = self.template_path("feeds.html")
        return self.render(request, templates, context)

    def feed(self, request, format, **kwargs):
        class BaseFeed(NewsFeed):
            title = getattr(request, "tenant", None) or kwargs.get("node")
            link = self.reverse("feeds")

        class AtomNewsFeed(BaseFeed):
            feed_type = Atom1Feed

        class RssNewsFeed(BaseFeed):
            feed_type = ExtendedRSSFeed

        feed_class = {
            "atom": AtomNewsFeed,
            "rss": RssNewsFeed,
        }
        return feed_class[format]()(request)


news = NewsSite()
