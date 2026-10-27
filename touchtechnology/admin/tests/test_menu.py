"""
The admin's menu: which components it shows each person, and what deciding
that costs a page.

A protected component is shown to a person who holds a permission in its
application: over the whole application, over one of its objects, or through
a group. A component that is not protected is shown to every member of staff.
"""

from django.contrib.auth.models import Group
from guardian.shortcuts import assign_perm
from test_plus import TestCase

from touchtechnology.admin.sites import site
from touchtechnology.admin.tests.shells import IconMixin, per_shell
from touchtechnology.common.tests.factories import StaffFactory, SuperUserFactory
from touchtechnology.content.models import Page
from touchtechnology.news.admin import NewsAdminComponent
from touchtechnology.news.tests.factories import ArticleFactory

#: The demo project's components that the menu lists: the name of each one's
#: first page, its label, and its icon in the Workbook and the Explorer.
COMPONENTS = {
    "auth": ("admin:auth:index", "Users &amp; Groups", "users", "group"),
    "content": ("admin:content:index", "Content", "file-text", "sitemap"),
    "news": ("admin:news:index", "News", "newspaper", "article"),
    "competition": (
        "admin:fixja:index",
        "Tournament Control",
        "trophy",
        "competition",
    ),
    "enrolment": ("admin:enrolment:index", "Enrolment", "graduation-cap", "schoolyear"),
}


class MoreNews(NewsAdminComponent):
    """
    One more protected component, for a test to register. It links to the
    News component's pages: the site's addresses were settled before the test
    runs, and only the components it was built with have any.
    """


class MenuMixin(IconMixin):
    def menu_entry(self, component):
        """The menu's link to ``component``, as the shell draws it."""
        url_name, label, workbook, explorer = COMPONENTS[component]
        url = self.reverse(url_name)
        return self.by_shell(
            workbook=(
                f'<a class="wb-nav-head" href="{url}">'
                f"{self.icon(workbook)}<span>{label}</span></a>"
            ),
            explorer=(
                f'<a class="area" href="{url}">'
                f"{self.icon(explorer)}<span>{label}</span></a>"
            ),
        )

    def section_entry(self, url_name, label, workbook, explorer):
        """The rail's link to a section of a component, as the shell draws it."""
        url = self.reverse(url_name)
        return self.by_shell(
            workbook=(
                f'<a class="wb-node-link" href="{url}" title="{label}">'
                f'{self.icon(workbook)}<span class="wb-node-label">{label}</span></a>'
            ),
            explorer=(
                f'<a class="node-link" href="{url}">'
                f'{self.icon(explorer)}<span class="node-label">{label}</span></a>'
            ),
        )

    def assertMenu(self, user, *shown):
        """The home page's menu shows ``user`` the components ``shown``, no other."""
        with self.login(user):
            self.get_check_200("admin:index")
        for component in shown:
            with self.subTest(shown=component):
                self.assertResponseContains(self.menu_entry(component))
        for component in COMPONENTS.keys() - set(shown):
            with self.subTest(hidden=component):
                self.assertResponseNotContains(self.menu_entry(component))


@per_shell
class SuperuserMenuTests(MenuMixin, TestCase):
    user_factory = SuperUserFactory

    def test_every_component_is_shown(self):
        self.assertMenu(self.make_user("superuser"), *COMPONENTS)


@per_shell
class StaffMenuTests(MenuMixin, TestCase):
    """
    News is protected and Content is not: a member of staff is shown News when
    they hold a permission in its application, however they hold it.
    """

    user_factory = StaffFactory

    @classmethod
    def setUpTestData(cls):
        cls.staff = cls.make_user("staff")
        cls.module_editor = cls.make_user("module", perms=["news.change_article"])
        cls.object_editor = cls.make_user("object")
        assign_perm("news.change_article", cls.object_editor, ArticleFactory.create())
        editors = Group.objects.create(name="Editors")
        assign_perm("news.change_article", editors)
        cls.group_editor = cls.make_user("group")
        cls.group_editor.groups.add(editors)

    def test_a_permission_over_the_application(self):
        self.assertMenu(self.module_editor, "content", "news")

    def test_a_permission_over_one_object(self):
        self.assertMenu(self.object_editor, "content", "news")

    def test_a_permission_through_a_group(self):
        self.assertMenu(self.group_editor, "content", "news")

    def test_no_permission(self):
        self.assertMenu(self.staff, "content")


@per_shell
class SectionMenuTests(MenuMixin, TestCase):
    """
    A section of a component's menu may name a permission, and the rail then
    draws it only for a person who holds it. Content's Media section takes
    ``content.view_file``; its Sitemap section is drawn for every member of
    staff the component is shown to.
    """

    user_factory = StaffFactory

    @classmethod
    def setUpTestData(cls):
        cls.staff = cls.make_user("staff")
        cls.viewer = cls.make_user("viewer", perms=["content.view_file"])

    def sitemap(self):
        return self.section_entry("admin:content:index", "Sitemap", "folder", "sitemap")

    def media(self):
        return self.section_entry(
            "admin:content:media:list", "Media", "folder", "image"
        )

    def test_a_person_who_holds_the_permission_is_shown_the_section(self):
        with self.login(self.viewer):
            self.get_check_200("admin:index")
        self.assertResponseContains(self.sitemap())
        self.assertResponseContains(self.media())

    def test_a_person_without_the_permission_is_not_shown_the_section(self):
        with self.login(self.staff):
            self.get_check_200("admin:index")
        self.assertResponseContains(self.sitemap())
        self.assertResponseNotContains(self.media())


@per_shell
class MenuQueryTests(TestCase):
    """
    What the home page costs a member of staff who holds no permission in a
    protected component's application: the same whether they hold an object
    permission elsewhere or nothing, and however many components there are.
    None of it is spent on the widgets of a component the menu does not show.
    """

    user_factory = StaffFactory

    @classmethod
    def setUpTestData(cls):
        cls.staff = cls.make_user("staff")
        cls.editor = cls.make_user("editor")
        assign_perm("content.change_page", cls.editor, Page.objects.create())
        cls.viewer = cls.make_user("viewer", perms=["content.view_file"])

    def assertHomeQueries(self, user):
        with self.login(user):
            # The first request fills the caches the site keeps from one
            # request to the next; measure the home page after that.
            self.get_check_200("admin:index")
            # The person's permissions in the applications of the components
            # are asked for once, whichever shell draws the menu.
            with self.assertNumQueries(6):
                self.get("admin:index")

    def test_a_person_with_an_object_permission(self):
        self.assertHomeQueries(self.editor)

    def test_a_person_with_no_permission(self):
        self.assertHomeQueries(self.staff)

    def test_a_person_with_a_permission_a_section_names(self):
        self.assertHomeQueries(self.viewer)

    def test_one_more_protected_component(self):
        site.register(MoreNews)
        self.addCleanup(site.unregister, MoreNews)
        self.assertHomeQueries(self.editor)
