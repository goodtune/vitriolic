from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site

from touchtechnology.content.middleware import SitemapNodeMiddleware


class WarmCachesMixin:
    """
    Django keeps the current site and every content type it looks up for the
    life of the process, and ``SitemapNodeMiddleware`` caches the URL tree it
    builds from the sitemap until a node changes. A query budget counted with
    those caches cold depends on which tests ran before it, so warm them
    first: the count is then the same alone, first in a worker, or deep in the
    full suite.
    """

    def warm_caches(self):
        Site.objects.get_current()
        ContentType.objects.get_for_models(*apps.get_models())
        SitemapNodeMiddleware.dehydrated_urlpatterns()
