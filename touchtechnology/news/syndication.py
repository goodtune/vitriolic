from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Rss201rev2Feed

from touchtechnology.news.models import Article


class ExtendedRSSFeed(Rss201rev2Feed):
    """
    Create a type of RSS feed that has content:encoded elements.
    """

    content_type = "text/xml; charset=utf-8"

    def root_attributes(self):
        attrs = super().root_attributes()
        attrs["xmlns:content"] = "http://purl.org/rss/1.0/modules/content/"
        return attrs

    def add_item_elements(self, handler, item):
        super().add_item_elements(handler, item)
        handler.addQuickElement("content:encoded", item["content_encoded"])


class NewsFeed(Feed):
    def items(self):
        return Article.objects.live().prefetch_related("categories")

    def item_categories(self, item):
        return [c.title for c in item.categories.all()]

    def item_description(self, item):
        return item.abstract

    def item_link(self, item):
        return item.get_absolute_url()

    def item_pubdate(self, item):
        return item.published

    def item_extra_kwargs(self, item):
        return {
            "content_encoded": f"<blockquote>{item.abstract}</blockquote>\n{item.copy}"
        }
