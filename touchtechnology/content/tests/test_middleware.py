from unittest import mock

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import override_settings
from django.urls.resolvers import _get_cached_resolver, get_ns_resolver
from guardian.conf import settings as guardian_settings
from test_plus.test import TestCase

from touchtechnology.admin.tests.tenancy import as_tenant, schema_context
from touchtechnology.common.models import SitemapNode
from touchtechnology.common.tests.factories import UserFactory
from touchtechnology.content.middleware import DEHYDRATED_URLPATTERNS_KEY
from touchtechnology.content.models import Page, PageContent

# The project's own cache could be a dummy that keeps nothing, which hides a
# cached URL tree that is never thrown away, so these tests use a real one.
URLPATTERNS_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "touchtechnology.content.tests.urlpatterns",
    },
}


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
            f"`_get_cached_resolver` cache grew by {growth} entries over 10 requests",
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
            f"`get_ns_resolver` cache grew by {growth} entries over 10 requests",
        )


@override_settings(LOGIN_URL="accounts:login")
class SitemapNodeRestrictToGroupsTests(TestCase):
    """
    A node restricted to one or more groups is only served to a signed in
    visitor who belongs to every one of them. An anonymous visitor is sent to
    sign in, and then comes back to the page they asked for.
    """

    user_factory = UserFactory

    @classmethod
    def setUpTestData(cls):
        # The URL patterns for the sitemap are cached between requests, and
        # the database is rolled back when the class finishes, so do not leave
        # nodes behind for the next test class to find.
        cls.addClassCleanup(cache.delete, DEHYDRATED_URLPATTERNS_KEY)

        cls.group = Group.objects.create(name="Members")

        home = SitemapNode.objects.create(title="Home", slug="home")

        restricted = Page.objects.create()
        PageContent.objects.create(
            page=restricted, sequence=1, copy="<p>Members only copy</p>"
        )
        cls.restricted = SitemapNode.objects.create(
            title="Members Area", slug="members", parent=home, object=restricted
        )
        cls.restricted.restrict_to_groups.add(cls.group)

        public = Page.objects.create()
        PageContent.objects.create(page=public, sequence=1, copy="<p>Anyone copy</p>")
        cls.public = SitemapNode.objects.create(
            title="Everyone Area", slug="everyone", parent=home, object=public
        )

        # The names of the URLs for nodes only exist in the URL configuration
        # the middleware builds for each request, so a node is requested by
        # its own absolute URL.
        cls.restricted_url = cls.restricted.get_absolute_url()
        cls.public_url = cls.public.get_absolute_url()

    def test_anonymous_is_redirected_to_sign_in(self):
        # ``assertLoginRequired`` expects the redirect to ``LOGIN_URL``, which
        # is overridden for this class to be where the middleware sends
        # visitors, and it fetches that sign in page to be sure it is served.
        self.assertLoginRequired(self.restricted_url)

    @override_settings(
        ROOT_URLCONF="touchtechnology.content.tests.urls", LOGIN_URL="/p/login/"
    )
    def test_anonymous_is_redirected_to_protected_sign_in_without_accounts_site(self):
        # A project that does not mount an ``AccountsSite`` of its own still
        # has the one the middleware adds to the sitemap under ``p/``, and that
        # prefix is the middleware's own, so there is no name to reverse.
        self.assertLoginRequired(self.restricted_url)

    def test_sign_in_page_returns_the_visitor_to_the_page(self):
        self.get(self.restricted_url, follow=True)

        self.assertResponseContains(
            f'<input type="hidden" name="next" value="{self.restricted_url}">'
        )

    def test_member_signs_in_and_lands_on_the_page(self):
        member = self.make_user("member")
        member.groups.add(self.group)

        self.post(
            "accounts:login",
            data={
                "username": member.username,
                "password": "password",
                "next": self.restricted_url,
            },
            follow=True,
        )

        self.assertResponseContains("<p>Members only copy</p>")

    def test_signed_in_non_member_is_forbidden(self):
        with self.login(self.make_user("outsider")):
            self.get(self.restricted_url)

        self.assert_http_403_forbidden()

    @mock.patch.object(guardian_settings, "RENDER_403", True)
    def test_signed_in_non_member_is_shown_the_403_template(self):
        with self.login(self.make_user("outsider")):
            self.get(self.restricted_url)

        self.assert_http_403_forbidden()
        self.assertResponseTemplateUsed("403.html")
        self.assertResponseHeaders({"Content-Type": "text/html; charset=utf-8"})

    @mock.patch.object(guardian_settings, "TEMPLATE_403", "missing/403.html")
    @mock.patch.object(guardian_settings, "RENDER_403", True)
    def test_signed_in_non_member_is_forbidden_when_403_template_is_missing(self):
        with self.login(self.make_user("outsider")):
            self.get(self.restricted_url)

        self.assert_http_403_forbidden()

    @mock.patch.object(guardian_settings, "RAISE_403", True)
    def test_signed_in_non_member_is_denied_permission(self):
        with self.login(self.make_user("outsider")):
            self.get(self.restricted_url)

        self.assert_http_403_forbidden()

    def test_member_is_served_the_page(self):
        member = self.make_user("member")
        member.groups.add(self.group)

        with self.login(member):
            self.get(self.restricted_url)

        self.assert_http_200_ok()
        self.assertResponseContains("<p>Members only copy</p>")

    def test_unrestricted_page_is_served_to_anonymous(self):
        self.get(self.public_url)

        self.assert_http_200_ok()
        self.assertResponseContains("<p>Anyone copy</p>")


class UrlpatternsCacheTestMixin:
    """
    The middleware caches the URL tree it builds from the sitemap. Saving or
    deleting a node throws that tree away, so the next request is served the
    change rather than the tree from before it.
    """

    @classmethod
    def setUpTestData(cls):
        cls.home = SitemapNode.objects.create(title="Home", slug="home")
        cls.home_url = cls.home.get_absolute_url()

    def setUp(self):
        super().setUp()
        self.addCleanup(cache.clear)

    def add_page(self, slug, copy):
        page = Page.objects.create()
        PageContent.objects.create(page=page, sequence=1, copy=copy)
        return SitemapNode.objects.create(
            title=slug.title(), slug=slug, parent=self.home, object=page
        )

    def add_folder(self, slug):
        return SitemapNode.objects.create(
            title=slug.title(), slug=slug, parent=self.home
        )


@override_settings(CACHES=URLPATTERNS_CACHES)
class UrlpatternsCacheTests(UrlpatternsCacheTestMixin, TestCase):
    def test_saved_page_is_served_straight_away(self):
        # A visit before the page exists caches the tree without it.
        self.get(self.home_url)
        node = self.add_page("fresh", "<p>Fresh copy</p>")

        self.get(node.get_absolute_url())

        self.assert_http_200_ok()
        self.assertResponseContains("<p>Fresh copy</p>")

    def test_deleted_folder_is_gone_straight_away(self):
        folder = self.add_folder("archive")
        url = folder.get_absolute_url()
        # A visit to the folder caches the tree with it.
        self.get(url)
        folder.delete()

        self.get(url)

        self.assert_http_404_not_found()


@as_tenant
@override_settings(CACHES=URLPATTERNS_CACHES)
class TenantUrlpatternsCacheTests(UrlpatternsCacheTestMixin, TestCase):
    """
    Each tenant's tree is cached apart from the others. Saving or deleting a
    node throws away the tree of the tenant whose schema it is saved in, and
    leaves the other tenants' trees alone.

    The tenants share the one schema of the test database, so a node saved
    for one tenant is in every tenant's tree when that tree is built again.
    """

    def test_saved_page_is_served_to_its_tenant_straight_away(self):
        with schema_context("alpha"):
            self.get(self.home_url)
            node = self.add_page("fresh", "<p>Fresh copy</p>")

            self.get(node.get_absolute_url())

        self.assert_http_200_ok()
        self.assertResponseContains("<p>Fresh copy</p>")

    def test_saved_page_leaves_the_other_tenants_tree_alone(self):
        with schema_context("bravo"):
            self.get(self.home_url)
        with schema_context("alpha"):
            node = self.add_page("fresh", "<p>Fresh copy</p>")

        # The page could only be found for bravo if its tree were built again.
        with schema_context("bravo"):
            self.get(node.get_absolute_url())

        self.assert_http_404_not_found()

    def test_deleted_folder_is_gone_for_its_tenant_straight_away(self):
        with schema_context("alpha"):
            folder = self.add_folder("archive")
            url = folder.get_absolute_url()
            self.get(url)
            folder.delete()

            self.get(url)

        self.assert_http_404_not_found()
