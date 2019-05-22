from __future__ import unicode_literals

import magic
from dateutil.relativedelta import relativedelta
from django.conf.urls import include, url
from django.contrib.syndication.views import Feed
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.feedgenerator import Atom1Feed, Rss201rev2Feed
from touchtechnology.common.sites import Application
from touchtechnology.news.app_settings import PAGINATE_BY
from touchtechnology.news.decorators import (
    date_view, last_modified_article, news_last_modified,
)
from touchtechnology.news.forms import ConfigurationForm
from touchtechnology.news.models import Article, Category

YEAR_DELTA = relativedelta(years=1)
MONTH_DELTA = relativedelta(months=1)
DAY_DELTA = relativedelta(days=1)


class NewsSite(Application):

    kwargs_form_class = ConfigurationForm

    def __init__(self, name='news', app_name='news', **kwargs):
        self.node = kwargs.get('node')  # store the node for future reference
        super(NewsSite, self).__init__(name=name, app_name=app_name, **kwargs)

    def get_urls(self):
        urls = [
            url(r'^archive/$', self.archive_index, name='archive'),
            url(r'^(?P<year>\d{4})/', include([
                url(r'^$', self.archive_year, name='year'),
                url(r'^(?P<month>[a-z]{3})/', include([
                    url(r'^$', self.archive_month, name='month'),
                    url(r'^(?P<day>\d{1,2})/', include([
                        url(r'^$', self.archive_day, name='day'),
                        url(r'^(?P<slug>[^/]+)/$',
                            self.article, name='article'),
                    ])),
                ])),
            ])),
        ]

        feeds = [
            url(r'^feeds/', include([
                url(r'^$', self.feeds, name='feeds'),
                url(r'^(?P<format>(atom|rss))/$',
                    self.feed, name='feed'),
            ])),
        ]

        if self.kwargs:
            urlpatterns = [
                url(r'^$', self.list_articles, kwargs=self.kwargs,
                    name='category-index'),
                url(r'^', include(urls), kwargs=self.kwargs),
                url(r'^', include(feeds)),
            ]
        else:
            urlpatterns = [
                url(r'^$', self.index, name='index'),
                url(r'^', include(urls)),
                url(r'^', include(feeds)),
                url(r'^(?P<category>[-\w]+)/$', self.list_articles,
                    name='category-index'),
            ]

        return urlpatterns

    @property
    def urls(self):
        return self.get_urls(), self.app_name, self.name

    @property
    def categories(self):
        return Category.objects.all()

    @news_last_modified
    def index(self, request, category=None, *args, **kwargs):
        context = {
            'object_list': Article.objects.live()[:PAGINATE_BY],
        }
        context.update(kwargs)
        return self.render(request, 'touchtechnology/news/index.html', context)

    @news_last_modified
    def list_articles(self, request, category=None, *args, **kwargs):
        articles = Article.objects.live()
        templates = self.template_path('list_articles.html', category)

        extra_context = {}
        extra_context.update(kwargs)

        if category is not None:
            category = get_object_or_404(Category, slug=category)
            articles = articles.filter(categories=category)
            extra_context['category'] = category

        context = {
            'object_list': articles,
        }
        context.update(extra_context)

        return self.render(request, templates, context)

    @date_view
    @last_modified_article
    def article(self, request, date, slug, category=None, *args, **kwargs):
        date_range = (date, date + DAY_DELTA)
        article = get_object_or_404(Article, slug=slug,
                                    published__range=date_range)
        context = {
            'article': article,
            'category': category,
        }
        context.update(kwargs)
        templates = self.template_path('article.html', category)
        return self.render(request, templates, context)

    @date_view
    @last_modified_article
    def archive_day(self, request, date, category=None, *args, **kwargs):
        queryset = Article.objects.live().filter(
            published__range=(date, date + DAY_DELTA))
        context = {
            'day': date,
            'object_list': queryset,
        }
        context.update(kwargs)
        templates = ['touchtechnology/news/archive/day.html']
        return self.render(request, templates, context)

    @date_view
    @last_modified_article
    def archive_month(self, request, date, category=None, *args, **kwargs):
        queryset = Article.objects.live().filter(
            published__range=(date, date + MONTH_DELTA))
        try:
            date_list = queryset.datetimes('published', 'day',
                                           tzinfo=timezone.utc)
        except AttributeError:
            date_list = queryset.dates('published', 'day')
        context = {
            'date_list': date_list,
            'month': date,
            'object_list': queryset,
        }
        context.update(kwargs)
        templates = ['touchtechnology/news/archive/month.html']
        return self.render(request, templates, context)

    @date_view
    @last_modified_article
    def archive_year(self, request, date, category=None, *args, **kwargs):
        queryset = Article.objects.live().filter(
            published__range=(date, date + YEAR_DELTA))

        try:
            date_list = queryset.datetimes('published', 'month',
                                           tzinfo=timezone.utc)
        except AttributeError:
            date_list = queryset.dates('published', 'month')

        # compatibility with date_based.archive_year
        year = str(date.year)

        context = {
            'date_list': date_list,
            'year': year,
            'object_list': queryset,
        }
        context.update(kwargs)

        templates = ['touchtechnology/news/archive/year.html']
        return self.render(request, templates, context)

    def archive_index(self, request, *args, **kwargs):
        queryset = Article.objects.live()
        try:
            date_list = queryset.datetimes('published', 'year',
                                           tzinfo=timezone.utc)
        except AttributeError:
            date_list = queryset.dates('published', 'year')
        context = {
            'date_list': date_list,
            'latest': queryset.order_by('-published')[:15],
        }
        context.update(kwargs)
        templates = ['touchtechnology/news/archive/index.html']
        return self.render(request, templates, context)

    def feeds(self, request, *args, **kwargs):
        context = {
            'feeds': {
                'ATOM': 'atom',
                'RSS': 'rss',
            },
        }
        context.update(kwargs)
        templates = self.template_path('feeds.html')
        return self.render(request, templates, context)

    def feed(self, request, format, category=None, *args, **kwargs):
        class NewsFeed(Feed):
            title = kwargs.get('node') or getattr(request, 'tenant', None)
            link = self.reverse('feeds')

            def items(slf):
                live = Article.objects.live()
                if category is not None:
                    live = live.filter(categories__slug=category)
                return live.prefetch_related('categories')

            def item_categories(slf, item):
                return [c.title for c in item.categories.all()]

            def item_description(slf, item):
                return item.abstract

            def item_link(slf, item):
                date = item.published.date()
                args = (date.year, date.strftime('%b').lower(),
                        date.day, item.slug)
                return self.reverse('article', args=args)

            def item_pubdate(slf, item):
                return item.published

            def item_enclosure_url(slf, item):
                try:
                    return request.build_absolute_uri(item.image.url)
                except Exception:
                    pass

            def item_enclosure_length(slf, item):
                try:
                    return item.image.size
                except Exception:
                    pass

            def item_enclosure_mime_type(slf, item):
                try:
                    return magic.from_file(item.image.path, mime=True)
                except Exception:
                    pass

        class AtomNewsFeed(NewsFeed):
            feed_type = Atom1Feed

        class RssNewsFeed(NewsFeed):
            feed_type = Rss201rev2Feed

        feed_class = {
            'atom': AtomNewsFeed,
            'rss': RssNewsFeed,
        }
        return feed_class[format]()(request)


news = NewsSite()
