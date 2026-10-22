import os.path
import tempfile
from urllib.parse import parse_qs, urlsplit

from django.test import override_settings
from test_plus import TestCase

from touchtechnology.admin.tests.links import LinksMixin
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.models import SitemapNode
from touchtechnology.common.tests.factories import UserFactory
from touchtechnology.content.models import Chunk, Page, Placeholder
from touchtechnology.content.tests.factories import RedirectFactory


@per_shell
class ContentLinksTests(LinksMixin, TestCase):
    """Every link on the content pages leads to a page that answers."""

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.folder = SitemapNode.objects.create(title="Press", slug="press")
        self.page = SitemapNode.objects.create(
            title="About",
            slug="about",
            parent=self.folder,
            object=Page.objects.create(),
        )
        self.application = SitemapNode.objects.create(
            title="Shop",
            slug="shop",
            object=Placeholder.objects.get(namespace="context"),
            kwargs={"key": "value"},
        )
        self.redirect = RedirectFactory.create()
        self.chunk = Chunk.objects.create(slug="footer")

    def test_the_trail_and_sections_of_the_sitemap(self):
        with self.login(self.superuser):
            self.follow_links("admin:content:index", selector="nav a")
            self.follow_links(
                "admin:content:folder:edit", self.folder.pk, selector="nav a"
            )
            self.follow_links("admin:content:page:edit", self.page.pk, selector="nav a")
            self.follow_links(
                "admin:content:placeholder:edit",
                self.application.pk,
                selector="nav a",
            )

    def test_the_permissions_of_a_page(self):
        with self.login(self.superuser):
            self.follow_links("admin:content:page:perms", self.page.pk)

    def test_the_permissions_of_an_application(self):
        with self.login(self.superuser):
            self.follow_links("admin:content:placeholder:perms", self.application.pk)

    def test_the_permissions_of_a_redirect(self):
        with self.login(self.superuser):
            self.follow_links("admin:content:redirect:perms", self.redirect.pk)

    def test_the_permissions_of_a_chunk(self):
        with self.login(self.superuser):
            self.follow_links("admin:content:chunk:perms", self.chunk.pk)

    def test_the_media_section_when_nothing_has_been_uploaded(self):
        # A site that has never had a file uploaded has no media folder yet.
        with (
            tempfile.TemporaryDirectory() as root,
            override_settings(MEDIA_ROOT=os.path.join(root, "media")),
        ):
            with self.login(self.superuser):
                self.get_check_200("admin:content:media:list")
                self.assertResponseContains(
                    self.by_shell(
                        workbook=(
                            '<tr class="wb-table-empty"><td colspan="2">'
                            "This folder is empty. Upload a file or make a folder."
                            "</td></tr>"
                        ),
                        explorer=(
                            '<tr><td colspan="2" class="empty-state">'
                            "Nothing here yet. Upload a file or make a folder."
                            "</td></tr>"
                        ),
                    )
                )
                self.follow_links("admin:content:media:list", selector="nav a")

    def test_a_missing_folder_of_the_media_section_is_not_found(self):
        with tempfile.TemporaryDirectory() as root, override_settings(MEDIA_ROOT=root):
            with self.login(self.superuser):
                self.get("admin:content:media:edit", "gallery/")
        self.assert_http_404_not_found()


class ContentRedirectsTests(TestCase):
    """Saving or deleting a folder sends the person to a page that answers."""

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def test_adding_a_folder_returns_to_the_sitemap(self):
        with self.login(self.superuser):
            self.post(
                "admin:content:folder:add",
                data={
                    "title": "Press",
                    "enabled": "1",
                    "hidden_from_navigation": "0",
                    "hidden_from_sitemap": "0",
                    "slug_locked": "0",
                },
            )
        self.assert_http_302_found(url=self.reverse("admin:content:index"))

    def test_deleting_a_folder_returns_to_the_sitemap(self):
        folder = SitemapNode.objects.create(title="Press", slug="press")
        with self.login(self.superuser):
            self.post("admin:content:folder:delete", folder.pk)
        self.assert_http_302_found(url=self.reverse("admin:content:index"))

    def test_deleting_a_folder_returns_to_the_folder_it_was_in(self):
        parent = SitemapNode.objects.create(title="Press", slug="press")
        folder = SitemapNode.objects.create(
            title="Archive", slug="archive", parent=parent
        )
        with self.login(self.superuser):
            self.post("admin:content:folder:delete", folder.pk)
        self.assert_http_302_found()
        redirect = urlsplit(self.last_response.url)
        self.assertEqual(
            (redirect.path, parse_qs(redirect.query)),
            (self.reverse("admin:content:index"), {"r": [str(parent.pk)]}),
        )
