from django.urls.resolvers import _get_cached_resolver, get_ns_resolver
from test_plus.test import TestCase


class SitemapNodeMiddlewareMemoryLeakTest(TestCase):
    def test_resolver_cache_does_not_grow_per_request(self):
        sitemap_url = self.reverse("sitemap")
        self.client.get(sitemap_url)
        cache_size_before = _get_cached_resolver.cache_info().currsize

        for _ in range(10):
            self.client.get(sitemap_url)

        cache_size_after = _get_cached_resolver.cache_info().currsize
        growth = cache_size_after - cache_size_before
        self.assertEqual(
            growth,
            0,
            "`_get_cached_resolver` cache grew by %d entries over 10 requests" % growth,
        )

    def test_ns_resolver_cache_does_not_grow_per_request(self):
        sitemap_url = self.reverse("sitemap")
        self.client.get(sitemap_url)
        cache_size_before = get_ns_resolver.cache_info().currsize

        for _ in range(10):
            self.client.get(sitemap_url)

        cache_size_after = get_ns_resolver.cache_info().currsize
        growth = cache_size_after - cache_size_before
        self.assertEqual(
            growth,
            0,
            "`get_ns_resolver` cache grew by %d entries over 10 requests" % growth,
        )
