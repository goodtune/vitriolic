from unittest import mock

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import override_settings
from django.urls.resolvers import _get_cached_resolver, get_ns_resolver
from guardian.conf import settings as guardian_settings
from test_plus.test import TestCase

from touchtechnology.common.models import SitemapNode
from touchtechnology.common.tests.factories import UserFactory
from touchtechnology.content.middleware import DEHYDRATED_URLPATTERNS_KEY
from touchtechnology.content.models import Page, PageContent


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

    def test_anonymous_is_redirected_to_sign_in(self):
        url = self.restricted.get_absolute_url()
        sign_in = self.reverse("accounts:login")

        response = self.get(url)

        # ``assertRedirects`` goes on to fetch the sign in page, so the target
        # of the redirect must exist and be served.
        self.assertRedirects(response, "%s?next=%s" % (sign_in, url))

    @override_settings(ROOT_URLCONF="touchtechnology.content.tests.urls")
    def test_anonymous_is_redirected_to_protected_sign_in_without_accounts_site(self):
        # A project that does not mount an ``AccountsSite`` of its own still
        # has the one the middleware adds to the sitemap under ``p/``.
        url = self.restricted.get_absolute_url()

        response = self.get(url)

        self.assertRedirects(response, "/p/login/?next=%s" % url)

    def test_anonymous_sees_sign_in_form_that_returns_to_the_page(self):
        url = self.restricted.get_absolute_url()
        sign_in = self.reverse("accounts:login")

        response = self.get(url, follow=True)

        self.assertRedirects(response, "%s?next=%s" % (sign_in, url))
        self.assertResponseContains(
            '<input type="hidden" name="next" value="%s">' % url, response
        )

    def test_member_signs_in_and_lands_on_the_page(self):
        member = self.make_user("member")
        member.groups.add(self.group)
        url = self.restricted.get_absolute_url()

        response = self.post(
            "accounts:login",
            data={"username": "member", "password": "password", "next": url},
        )
        self.assertRedirects(response, url)

        self.assertResponseContains("<p>Members only copy</p>", self.get(url))

    def test_signed_in_non_member_is_forbidden(self):
        outsider = self.make_user("outsider")
        url = self.restricted.get_absolute_url()

        with self.login(outsider):
            self.get(url)

        self.response_403()

    @mock.patch.object(guardian_settings, "RENDER_403", True)
    def test_signed_in_non_member_is_shown_the_403_template(self):
        outsider = self.make_user("outsider")
        url = self.restricted.get_absolute_url()

        with self.login(outsider):
            response = self.get(url)

        self.response_403()
        self.assertResponseTemplateUsed("403.html")
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")

    @mock.patch.object(guardian_settings, "TEMPLATE_403", "missing/403.html")
    @mock.patch.object(guardian_settings, "RENDER_403", True)
    def test_signed_in_non_member_is_forbidden_when_403_template_is_missing(self):
        outsider = self.make_user("outsider")
        url = self.restricted.get_absolute_url()

        with self.login(outsider):
            self.get(url)

        self.response_403()

    @mock.patch.object(guardian_settings, "RAISE_403", True)
    def test_signed_in_non_member_is_denied_permission(self):
        outsider = self.make_user("outsider")
        url = self.restricted.get_absolute_url()

        with self.login(outsider):
            self.get(url)

        self.response_403()

    def test_member_is_served_the_page(self):
        member = self.make_user("member")
        member.groups.add(self.group)
        url = self.restricted.get_absolute_url()

        with self.login(member):
            self.get_check_200(url)

        self.assertResponseContains("<p>Members only copy</p>")

    def test_unrestricted_page_is_served_to_anonymous(self):
        self.get_check_200(self.public.get_absolute_url())

        self.assertResponseContains("<p>Anyone copy</p>")
