import magic
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

    def item_enclosure_url(self, item):
        try:
            return request.build_absolute_uri(item.image.url)
        except Exception:
            pass

    def item_enclosure_length(self, item):
        try:
            return item.image.size
        except Exception:
            pass

    def item_enclosure_mime_type(self, item):
        try:
            return magic.from_file(item.image.path, mime=True)
        except Exception:
            pass

    def item_extra_kwargs(self, item):
        return {
            "content_encoded": "<blockquote>%(abstract)s</blockquote>\n%(copy)s"
            % vars(item)
        }
