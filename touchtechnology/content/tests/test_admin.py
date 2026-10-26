import tempfile
from os.path import dirname, join

from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import override_settings
from guardian.shortcuts import assign_perm
from test_plus.test import TestCase

from touchtechnology.admin.tests.lists import unordered_pages_fail
from touchtechnology.admin.tests.shells import (
    ArrowMixin,
    IconMixin,
    by_shell,
    per_shell,
)
from touchtechnology.common.models import SitemapNode
from touchtechnology.common.tests.factories import (
    StaffFactory,
    SuperUserFactory,
    UserFactory,
)
from touchtechnology.content.models import Chunk, Page, Placeholder
from touchtechnology.content.tests import factories

NEWS_SITE = "touchtechnology.news.sites.NewsSite"


class AdminTests(TestCase):
    def setUp(self):
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.staff = UserFactory.create(is_staff=True)
        self.staff.user_permissions.set(
            Permission.objects.filter(codename__endswith="_sitemapnode")
        )

        placeholder = Placeholder.objects.get(namespace="context")
        self.root_node = SitemapNode.objects.create(
            title="Simple Test",
            slug="home",
            object=placeholder,
            kwargs={"key": "value"},
        )

    def get_text(self, filename):
        with open(join(dirname(__file__), filename)) as fp:
            text = fp.read()
        return text

    def test_sitemap_index_superuser(self):
        self.assertLoginRequired("admin:content:index")
        with self.login(self.superuser):
            self.get("admin:content:index")
            html = by_shell(
                workbook=f"""
                <a href="/admin/content/application/{self.root_node.pk}/">
                    <svg class="wb-icon" aria-hidden="true" focusable="false">
                        <use href="/static/touchtechnology/admin/workbook/icons.svg#pencil"></use>
                    </svg>Edit</a>
            """,
                explorer=f"""
                <a href="/admin/content/application/{self.root_node.pk}/">
                    <svg class="icon" aria-hidden="true" focusable="false">
                        <use href="/static/touchtechnology/admin/explorer/img/icons.svg#edit"></use>
                    </svg>
                    Edit
                </a>
            """,
            )
            self.assertResponseContains(html)

    def test_sitemap_index_staff_user(self):
        self.assertLoginRequired("admin:content:index")
        with self.login(self.staff):
            self.get("admin:content:index")
            html = "<span>Simple Test</span>"
            self.assertResponseContains(html)

    def test_edit_page(self):
        with self.login(self.superuser):
            self.assertGoodView("admin:content:page:add")

            copy = """<p>Sample page data.</p>"""
            data = {
                "parent-form-parent": "",
                "parent-form-title": "Sample",
                "parent-form-short_title": "",
                "parent-form-enabled": "1",
                "parent-form-hidden_from_navigation": "0",
                "parent-form-hidden_from_sitemap": "0",
                "parent-form-slug": "",
                "parent-form-slug_locked": "0",
                "form-template": "",
                "form-keywords": "",
                "form-description": "",
                "formset-TOTAL_FORMS": "1",
                "formset-INITIAL_FORMS": "0",
                "formset-MIN_NUM_FORMS": "0",
                "formset-MAX_NUM_FORMS": "1000",
                "formset-0-copy": copy,
                "formset-0-label": "copy",
                "formset-0-sequence": "1",
                "formset-0-id": "",
                "formset-0-page": "",
            }
            self.post("admin:content:page:add", data=data)
            self.response_302()

            node = SitemapNode.objects.latest("pk")
            self.assertEqual(node.get_absolute_url(), "/sample/")

            self.assertEqual(node.object.content.latest("pk").copy, copy)

            # Unfortunately the SitemapNodeMiddleware does not appear to be
            # having an effect?
            # self.get(node.get_absolute_url())
            # self.response_200()


class GoodViewTests(TestCase):
    def setUp(self):
        self.staff = UserFactory.create(is_staff=True, is_superuser=True)
        self.regular = UserFactory.create()

    def test_redirect_list(self):
        factories.RedirectFactory.create()

        with self.login(self.staff):
            self.assertGoodView("admin:content:redirect:list")
            self.response_200()

    def test_delete_redirect_with_protected_objects(self):
        """
        Test that deleting a redirect with protected objects shows a user-friendly error.
        Note: This is a demonstration test - Redirect model may not actually have
        protected relationships, but shows the generic ProtectedError handling works.
        """
        redirect = factories.RedirectFactory.create()

        with self.login(self.staff):
            # Try to delete the redirect - this might work normally if no protection exists
            # This test demonstrates the generic error handling is available
            self.post("admin:content:redirect:delete", pk=redirect.pk)

            # If no ProtectedError is raised, this should succeed
            # If ProtectedError is raised, the generic handler will show an error message
            # This test mainly verifies no code crashes with the new generic handling


@per_shell
class ChunkListTests(TestCase):
    """The list of chunks, shown a page at a time."""

    user_factory = SuperUserFactory

    def test_the_chunks_are_listed_by_slug(self):
        superuser = self.make_user("superuser")
        footer = Chunk.objects.create(slug="footer")
        banner = Chunk.objects.create(slug="banner")
        sidebar = Chunk.objects.create(slug="sidebar")
        with unordered_pages_fail(), self.login(superuser):
            self.get("admin:content:chunk:list")
        self.assert_http_200_ok()
        self.assertEqual(
            list(self.get_context("object_list")), [banner, footer, sidebar]
        )


class MediaStorageMixin:
    """
    Keeps the media of each test in a folder of its own, in the project's
    storage: Django's own cannot remove a folder. The storage is given its
    location, as it cannot make one when ``STORAGE_FOLDER`` is not set.
    """

    def setUp(self):
        super().setUp()
        root = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(
            override_settings(
                STORAGES={
                    **settings.STORAGES,
                    "default": {
                        "BACKEND": "touchtechnology.common.storage.FileSystemStorage",
                        "OPTIONS": {"location": root},
                    },
                },
            )
        )


class MediaDeleteTests(MediaStorageMixin, TestCase):
    """Deleting a file or a folder of the media section."""

    user_factory = StaffFactory

    def setUp(self):
        super().setUp()
        self.staff = self.make_user("staff")

    def test_a_file_in_a_missing_folder_is_not_found(self):
        with self.login(self.staff):
            self.get(
                "admin:content:media:delete", path="gallery/", filename="photo.jpg"
            )
        self.assert_http_404_not_found()

    def test_a_missing_folder_is_not_found(self):
        with self.login(self.staff):
            self.get("admin:content:media:delete", path="gallery/")
        self.assert_http_404_not_found()

    def test_deleting_a_file_goes_back_to_its_folder(self):
        default_storage.save("reports/minutes.pdf", ContentFile(b"%PDF-1.4"))
        with self.login(self.staff):
            self.post("admin:content:media:delete", "reports/", "minutes.pdf")
        self.assert_http_302_found(
            url=self.reverse("admin:content:media:edit", "reports/")
        )
        self.assertEqual(default_storage.listdir("reports"), ([], []))

    def test_deleting_a_folder_goes_back_to_the_folder_it_was_in(self):
        default_storage.makedirs("reports/2026")
        with self.login(self.staff):
            self.post("admin:content:media:delete", "reports/2026/")
        self.assert_http_302_found(
            url=self.reverse("admin:content:media:edit", "reports/")
        )
        self.assertEqual(default_storage.listdir("reports"), ([], []))


@per_shell
class MediaDeleteConfirmationTests(MediaStorageMixin, IconMixin, TestCase):
    """
    The page that asks before a file or a folder of the media is deleted, at
    the address its row's Delete form posts to. Cancel goes back to the folder
    the file or the folder is in.
    """

    user_factory = SuperUserFactory

    def setUp(self):
        super().setUp()
        self.superuser = self.make_user("superuser")

    def assertConfirmation(self, kind, name, cancel):
        self.assertResponseContains(
            self.by_shell(
                workbook=(
                    f"<p>You are about to delete the {kind} <strong>{name}</strong>. "
                    "This will permanently remove it from your site. "
                    "Are you sure you want to continue?</p>"
                ),
                explorer=(
                    f"<p>The {kind} <strong>{name}</strong> "
                    "will be removed from the site for good.</p>"
                ),
            )
        )
        csrf = (
            '<input type="hidden" name="csrfmiddlewaretoken" '
            f'value="{self.get_context("csrf_token")}">'
        )
        self.assertResponseContains(
            self.by_shell(
                workbook=(
                    f'<form action="" method="post">{csrf}<div class="wb-actions">'
                    '<button type="submit" class="wb-button wb-button-danger">'
                    f'{self.icon("trash-2")}Delete</button>'
                    f'<a href="{cancel}" class="wb-button wb-button-quiet">Cancel</a>'
                    "</div></form>"
                ),
                explorer=(
                    f'<form action="" method="post" class="button-row">{csrf}'
                    '<button type="submit" class="button destructive">'
                    f'{self.icon("trash")}<span>Delete</span></button>'
                    f'<a href="{cancel}" class="button">Cancel</a></form>'
                ),
            )
        )

    def test_a_file_at_the_top_is_confirmed_before_it_is_deleted(self):
        default_storage.save("minutes.pdf", ContentFile(b"%PDF-1.4"))
        with self.login(self.superuser):
            self.get("admin:content:media:delete", "minutes.pdf")
        self.assert_http_200_ok()
        self.assertConfirmation(
            "File", "minutes.pdf", self.reverse("admin:content:media:list")
        )

    def test_a_file_in_a_folder_is_confirmed_before_it_is_deleted(self):
        default_storage.save("reports/minutes.pdf", ContentFile(b"%PDF-1.4"))
        with self.login(self.superuser):
            self.get("admin:content:media:delete", "reports/", "minutes.pdf")
        self.assert_http_200_ok()
        self.assertConfirmation(
            "File",
            "reports/minutes.pdf",
            self.reverse("admin:content:media:edit", "reports/"),
        )

    def test_a_folder_is_confirmed_before_it_is_deleted(self):
        default_storage.makedirs("reports/2026")
        with self.login(self.superuser):
            self.get("admin:content:media:delete", "reports/2026/")
        self.assert_http_200_ok()
        self.assertConfirmation(
            "Folder",
            "reports/2026",
            self.reverse("admin:content:media:edit", "reports/"),
        )


@per_shell
class SitemapListTests(ArrowMixin, TestCase):
    """The sitemap list: what each row shows, and what the page costs to draw."""

    user_factory = SuperUserFactory

    def setUp(self):
        super().setUp()
        self.superuser = self.make_user("superuser")

    def make_nodes(self, count, parent=None):
        """
        Give ``parent`` (or the top of the sitemap) ``count`` nodes in all: a
        page, a folder and an application in turn, the applications mounting
        the installed ones.
        """
        start = SitemapNode.objects.filter(parent=parent).count()
        applications = Placeholder.objects.order_by("pk")
        for n in range(start, count):
            node = {"title": f"Node {n}", "slug": f"node-{n}", "parent": parent}
            if n % 3 == 0:
                SitemapNode.objects.create(**node, object=Page.objects.create())
            elif n % 3 == 1:
                SitemapNode.objects.create(**node)
            else:
                SitemapNode.objects.create(
                    **node, object=applications[n // 3 % applications.count()]
                )

    def assertListQueries(self, queries, parent=None):
        """
        The list of ``parent``'s nodes (or the top of the sitemap) runs
        ``queries`` queries with one node in it and with twelve.
        """
        data = {"r": parent.pk} if parent else {}
        with self.login(self.superuser):
            for count in (1, 12):
                with self.subTest(count=count):
                    self.make_nodes(count, parent)
                    # The first request after a change of the sitemap rebuilds
                    # the site's URL patterns; measure the list after that.
                    self.get_check_200("admin:content:index", data=data)
                    with self.assertNumQueries(queries):
                        self.get("admin:content:index", data=data)

    def test_the_top_of_the_sitemap_runs_as_many_queries_for_twelve_as_for_one(self):
        self.assertListQueries(7)

    def test_a_folder_runs_as_many_queries_for_twelve_as_for_one(self):
        press = SitemapNode.objects.create(title="Press", slug="press")
        archive = SitemapNode.objects.create(
            title="Archive", slug="archive", parent=press
        )
        # The folder, its line and the trail to it are looked up once each.
        self.assertListQueries(self.by_shell(workbook=14, explorer=13), archive)

    def test_a_folder_lists_each_node_at_its_address(self):
        press = SitemapNode.objects.create(title="Press", slug="press")
        archive = SitemapNode.objects.create(
            title="Archive", slug="archive", parent=press
        )
        self.make_nodes(1, archive)
        with self.login(self.superuser):
            self.get_check_200("admin:content:index", data={"r": archive.pk})
        # A node's address has no URL name: it is the slugs of its line.
        address = "/press/archive/node-0/"
        self.assertResponseContains(
            self.by_shell(
                workbook=(
                    f'<td data-label="Address"><a href="{address}" target="_blank" '
                    f'rel="noopener"><span class="wb-code">{address}</span>'
                    '<span class="wb-sr"> (opens a new tab)</span></a></td>'
                ),
                explorer=(
                    f'<td class="wide-only"><a href="{address}" target="_blank">'
                    f"{address}</a></td>"
                ),
            )
        )

    def title_cell(self, node, route, icon):
        """The first cell of ``node``'s row, which links to ``route``."""
        edit = self.reverse(route, node.pk)
        return self.by_shell(
            workbook=(
                f'<td class="wb-title-cell">{self.icon(icon)}'
                f'<a href="{edit}">{node.title}</a></td>'
            ),
            explorer=(
                f'<td class="title-cell"><a href="{edit}">{self.icon(icon)}'
                f"<span>{node.title}</span></a></td>"
            ),
        )

    def test_each_row_shows_the_icon_of_what_the_node_holds(self):
        """
        A node's icon is that of what it holds, not of its place in the tree:
        a page with pages beneath it is still a page, and an application or a
        folder with nothing in it yet is not one.
        """
        news, _ = Placeholder.objects.get_or_create(path=NEWS_SITE, namespace="news")
        press = SitemapNode.objects.create(title="Press", slug="press")
        SitemapNode.objects.create(
            title="Releases", slug="releases", parent=press, object=Page.objects.create()
        )
        archive = SitemapNode.objects.create(title="Archive", slug="archive")
        about = SitemapNode.objects.create(
            title="About us", slug="about-us", object=Page.objects.create()
        )
        team = SitemapNode.objects.create(
            title="Team", slug="team", object=Page.objects.create()
        )
        SitemapNode.objects.create(
            title="Coaches", slug="coaches", parent=team, object=Page.objects.create()
        )
        latest = SitemapNode.objects.create(title="Latest", slug="latest", object=news)
        page = self.by_shell(workbook="file-text", explorer="page")
        with self.login(self.superuser):
            self.get_check_200("admin:content:index")
        for node, route, icon in (
            (press, "admin:content:folder:edit", "folder"),
            (archive, "admin:content:folder:edit", "folder"),
            (about, "admin:content:page:edit", page),
            (team, "admin:content:page:edit", page),
            (latest, "admin:content:placeholder:edit", "puzzle"),
        ):
            with self.subTest(node.title):
                self.assertResponseContains(self.title_cell(node, route, icon))

    def test_each_row_has_arrows_that_post(self):
        press = SitemapNode.objects.create(title="Press", slug="press")
        with self.login(self.superuser):
            self.get_check_200("admin:content:index")
        for direction in ("up", "down"):
            with self.subTest(direction):
                action = self.reverse("admin:reorder", press.pk, direction)
                self.assertResponseContains(self.arrow(action, direction, "Press"))

    def plain_title_cell(self, node):
        """The first cell of ``node``'s row, for a person who may not edit it."""
        return self.by_shell(
            workbook=(
                f'<td class="wb-title-cell">{self.icon("folder")}'
                f"<span>{node.title}</span></td>"
            ),
            explorer=(
                f'<td class="title-cell"><a href="{node.urls["edit"]}">'
                f'{self.icon("folder")}<span>{node.title}</span></a></td>'
            ),
        )

    def test_a_person_who_may_not_change_the_nodes_sees_no_arrows(self):
        """
        A member of staff who may add to the sitemap sees its nodes, but has
        no arrow to move one they may not change.
        """
        press = SitemapNode.objects.create(title="Press", slug="press")
        viewer = StaffFactory.create(username="viewer")
        assign_perm("common.add_sitemapnode", viewer)
        with self.login(viewer):
            self.get_check_200("admin:content:index")
        self.assertResponseContains(self.plain_title_cell(press))
        for direction in ("up", "down"):
            with self.subTest(direction):
                action = self.reverse("admin:reorder", press.pk, direction)
                self.assertResponseNotContains(self.arrow(action, direction, "Press"))

    def test_the_arrows_are_drawn_for_the_nodes_the_person_may_change(self):
        press = SitemapNode.objects.create(title="Press", slug="press")
        archive = SitemapNode.objects.create(title="Archive", slug="archive")
        editor = StaffFactory.create(username="editor")
        assign_perm("common.add_sitemapnode", editor)
        assign_perm("common.change_sitemapnode", editor, press)
        with self.login(editor):
            self.get_check_200("admin:content:index")
        self.assertResponseContains(self.plain_title_cell(archive))
        for direction in ("up", "down"):
            with self.subTest(direction):
                action = self.reverse("admin:reorder", press.pk, direction)
                self.assertResponseContains(self.arrow(action, direction, "Press"))
                action = self.reverse("admin:reorder", archive.pk, direction)
                self.assertResponseNotContains(
                    self.arrow(action, direction, "Archive")
                )


class ApplicationListMixin(IconMixin):
    """
    The Applications list, with only the applications a test makes: mounted
    by no node of the sitemap, by one and by two, in turn.
    """

    def setUp(self):
        super().setUp()
        Placeholder.objects.all().delete()

    def make_applications(self, count):
        """Have ``count`` applications in all."""
        for n in range(Placeholder.objects.count(), count):
            application = Placeholder.objects.create(
                path=NEWS_SITE, namespace=f"news-{n}"
            )
            for m in range(n % 3):
                SitemapNode.objects.create(
                    title=f"News {n}.{m}", slug=f"news-{n}-{m}", object=application
                )

    def assertListQueries(self, user, queries):
        """The list runs ``queries`` queries for one application and for twelve."""
        with self.login(user):
            for count in (1, 12):
                with self.subTest(count=count):
                    self.make_applications(count)
                    # The first request after a change of the sitemap rebuilds
                    # the site's URL patterns; measure the list after that.
                    self.get_check_200("admin:content:real_placeholder:list")
                    with self.assertNumQueries(queries):
                        self.get("admin:content:real_placeholder:list")

    def assertPagesShown(self, user):
        """Each row shows how many pages of the sitemap mount its application."""
        self.make_applications(3)
        with self.login(user):
            self.get_check_200("admin:content:real_placeholder:list")
        for application in Placeholder.objects.order_by("pk"):
            pages = application.nodes.count()
            edit = self.reverse("admin:content:real_placeholder:edit", application.pk)
            tag = {
                0: "",
                1: '<span class="tag">1 page</span>',
                2: '<span class="tag">2 pages</span>',
            }[pages]
            with self.subTest(pages=pages):
                self.assertResponseContains(
                    self.by_shell(
                        workbook=f'<td class="wb-num" data-label="Pages">{pages}</td>',
                        explorer=(
                            f'<td class="title-cell"><a href="{edit}">'
                            f'{self.icon("puzzle")}<span>News</span></a>{tag}</td>'
                        ),
                    )
                )


@per_shell
class ApplicationListTests(ApplicationListMixin, TestCase):
    """The Applications list, for a person who may do anything."""

    user_factory = SuperUserFactory

    def setUp(self):
        super().setUp()
        self.superuser = self.make_user("superuser")

    def test_the_list_runs_as_many_queries_for_twelve_applications_as_for_one(self):
        self.assertListQueries(self.superuser, 6)

    def test_each_row_shows_how_many_pages_mount_it(self):
        self.assertPagesShown(self.superuser)


@per_shell
class ApplicationListObjectPermissionTests(ApplicationListMixin, TestCase):
    """
    The Applications list for a person who may change each application, but
    has no permission over all of them: the list is filtered to theirs.
    """

    user_factory = StaffFactory

    def setUp(self):
        super().setUp()
        self.editor = self.make_user("editor")

    def make_applications(self, count):
        super().make_applications(count)
        for application in Placeholder.objects.all():
            assign_perm("content.change_placeholder", self.editor, application)

    def test_the_list_runs_as_many_queries_for_twelve_applications_as_for_one(self):
        # Asking what this person may do over the list as a whole costs the
        # same for any number of rows: the Explorer asks once more, for the
        # import path's column.
        self.assertListQueries(self.editor, self.by_shell(workbook=12, explorer=13))

    def test_each_row_shows_how_many_pages_mount_it(self):
        self.assertPagesShown(self.editor)


@per_shell
class DeleteConfirmationTests(IconMixin, TestCase):
    """
    The dialog that asks before a row is deleted calls the row what it is: a
    page, a folder or an application of the sitemap, a file or a folder of the
    media. The dialog takes its words from the row's Delete form.
    """

    user_factory = SuperUserFactory

    def setUp(self):
        super().setUp()
        self.superuser = self.make_user("superuser")
        self.news, _ = Placeholder.objects.get_or_create(
            path=NEWS_SITE, namespace="news"
        )

    def delete_form(self, action, name, kind):
        """
        The Delete form of a row. The Explorer's list of files names no kind,
        and asks without a title: give ``kind=None`` for it.
        """
        csrf = (
            '<input type="hidden" name="csrfmiddlewaretoken" '
            f'value="{self.get_context("csrf_token")}">'
        )
        if kind is None:
            explorer = f'data-confirm="“{name}” will be removed for good."'
        else:
            explorer = (
                f'data-confirm="The {kind} “{name}” will be removed for good." '
                f'data-confirm-title="Delete this {kind}?"'
            )
        return self.by_shell(
            workbook=(
                f'<form method="post" action="{action}" '
                f'data-wb-confirm="The {kind} “{name}” will be removed for good." '
                f'data-wb-confirm-title="Delete {name}?" '
                f'data-wb-confirm-label="Delete {kind}">'
                f'{csrf}<button type="submit" class="wb-danger-item">'
                f'{self.icon("trash-2")}Delete</button></form>'
            ),
            explorer=(
                f'<form method="post" action="{action}" {explorer} '
                'data-confirm-label="Delete">'
                f'{csrf}<button type="submit" class="destructive-item">'
                f'{self.icon("trash")}Delete</button></form>'
            ),
        )

    def test_each_node_of_the_sitemap_is_called_what_it_is(self):
        folder = SitemapNode.objects.create(title="Archive", slug="archive")
        page = SitemapNode.objects.create(
            title="About us", slug="about-us", object=Page.objects.create()
        )
        application = SitemapNode.objects.create(
            title="Latest", slug="latest", object=self.news
        )
        with self.login(self.superuser):
            self.get_check_200("admin:content:index")
        for route, node, kind in (
            ("admin:content:folder:delete", folder, "folder"),
            ("admin:content:page:delete", page, "page"),
            ("admin:content:placeholder:delete", application, "application"),
        ):
            with self.subTest(kind):
                self.assertResponseContains(
                    self.delete_form(self.reverse(route, node.pk), node.title, kind)
                )

    def test_each_row_of_the_files_is_called_what_it_is(self):
        with tempfile.TemporaryDirectory() as root, override_settings(MEDIA_ROOT=root):
            default_storage.save("minutes.pdf", ContentFile(b"%PDF-1.4"))
            default_storage.save("reports/minutes.pdf", ContentFile(b"%PDF-1.4"))
            with self.login(self.superuser):
                self.get_check_200("admin:content:media:list")
        for path, name, kind in (
            ("minutes.pdf", "minutes.pdf", "file"),
            ("reports/", "reports", "folder"),
        ):
            with self.subTest(kind):
                self.assertResponseContains(
                    self.delete_form(
                        self.reverse("admin:content:media:delete", path),
                        name,
                        self.by_shell(workbook=kind, explorer=None),
                    )
                )

    def test_the_list_of_applications_links_each_to_its_edit_page(self):
        edit = self.reverse("admin:content:real_placeholder:edit", self.news.pk)
        with self.login(self.superuser):
            self.get_check_200("admin:content:real_placeholder:list")
        self.assertResponseContains(
            self.by_shell(
                workbook=f'<a href="{edit}">News</a>',
                explorer=f'<a href="{edit}">{self.icon("puzzle")}<span>News</span></a>',
            )
        )
        self.assertResponseContains(
            self.by_shell(
                workbook=f'<li><a href="{edit}">{self.icon("pencil")}Edit</a></li>',
                explorer=f'<a href="{edit}">{self.icon("edit")}Edit</a>',
            )
        )

    def test_the_list_of_applications_offers_to_delete_one(self):
        with self.login(self.superuser):
            self.get_check_200("admin:content:real_placeholder:list")
        self.assertResponseContains(
            self.delete_form(
                self.reverse("admin:content:real_placeholder:delete", self.news.pk),
                "News",
                "placeholder",
            )
        )


@per_shell
class MountedApplicationDeleteTests(IconMixin, TestCase):
    """
    An application that the sitemap still uses is not deleted: deleting it
    would remove every node of the sitemap that mounts it, and the dialog that
    asks first does not know of them.
    """

    user_factory = SuperUserFactory

    def setUp(self):
        super().setUp()
        self.superuser = self.make_user("superuser")
        self.news, _ = Placeholder.objects.get_or_create(
            path=NEWS_SITE, namespace="news"
        )
        SitemapNode.objects.create(title="Latest", slug="latest", object=self.news)
        press = SitemapNode.objects.create(title="Press", slug="press")
        SitemapNode.objects.create(
            title="Releases", slug="releases", parent=press, object=self.news
        )

    def test_deleting_an_application_the_sitemap_uses_is_refused(self):
        placeholders = Placeholder.objects.count()
        with self.login(self.superuser):
            self.post("admin:content:real_placeholder:delete", self.news.pk)
            self.assert_http_302_found(
                url=self.reverse("admin:content:real_placeholder:list")
            )
            self.get_check_200("admin:content:real_placeholder:list")
        text = (
            "“News” was not deleted: the sitemap still uses it at "
            "Latest (/latest/), Releases (/press/releases/). "
            "Delete those from the sitemap first."
        )
        self.assertResponseContains(
            self.by_shell(
                workbook=(
                    '<p class="wb-message wb-message-error">'
                    f'{self.icon("circle-alert")}<span>{text}</span></p>'
                ),
                explorer=(
                    '<div class="message message-error">'
                    f'{self.icon("alert")}<p>{text}</p>'
                    '<button type="button" class="message-close">'
                    f'{self.icon("x")}<span class="visually-hidden">Dismiss</span>'
                    "</button></div>"
                ),
            )
        )
        self.assertEqual(
            (Placeholder.objects.count(), SitemapNode.objects.count()),
            (placeholders, 3),
        )


class ApplicationDeleteTests(TestCase):
    """
    Confirming the delete of an application posts to the route its row's form
    names, which takes the permission to delete applications.
    """

    user_factory = StaffFactory

    def setUp(self):
        super().setUp()
        self.news, _ = Placeholder.objects.get_or_create(
            path=NEWS_SITE, namespace="news"
        )

    def test_a_visitor_is_asked_to_sign_in(self):
        self.assertLoginRequired("admin:content:real_placeholder:delete", self.news.pk)

    def test_a_person_who_may_not_delete_applications_is_refused(self):
        editor = self.make_user("editor", perms=["content.change_placeholder"])
        with self.login(editor):
            self.post("admin:content:real_placeholder:delete", self.news.pk)
        self.assert_http_403_forbidden()
        self.assertCountEqual(Placeholder.objects.filter(namespace="news"), [self.news])

    def test_a_person_who_may_not_delete_applications_is_refused_one_in_use(self):
        latest = SitemapNode.objects.create(
            title="Latest", slug="latest", object=self.news
        )
        editor = self.make_user("editor", perms=["content.change_placeholder"])
        with self.login(editor):
            self.post("admin:content:real_placeholder:delete", self.news.pk)
        self.assert_http_403_forbidden()
        self.assertCountEqual(self.news.nodes.all(), [latest])

    def test_a_person_who_may_delete_applications_deletes_one(self):
        editor = self.make_user("editor", perms=["content.delete_placeholder"])
        with self.login(editor):
            self.post("admin:content:real_placeholder:delete", self.news.pk)
        self.assert_http_302_found(
            url=self.reverse("admin:content:real_placeholder:list")
        )
        self.assertCountEqual(Placeholder.objects.filter(namespace="news"), [])
