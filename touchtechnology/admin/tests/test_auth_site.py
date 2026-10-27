from datetime import datetime, timezone
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils.functional import SimpleLazyObject
from test_plus import TestCase as PlusTestCase

from touchtechnology.admin.explorer import Explorer
from touchtechnology.admin.mixins import AdminUrlMixin
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.admin.trail import models_by_namespace
from touchtechnology.common.tests import factories


class TestCase(PlusTestCase):
    def setUp(self):
        super().setUp()
        self.staff = factories.UserFactory.create(is_staff=True)
        self.superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)

    def get_generic_200(self, url_name, user, in_context, template, **kw):
        self.assertLoginRequired(url_name, **kw)
        with self.login(user):
            self.get(url_name, **kw)
            self.assert_http_200_ok()
            for key in in_context:
                self.assertInContext(key)
            self.assertTemplateUsed(self.last_response, template)


@per_shell
class AuthSiteUserTests(TestCase):
    def test_index(self):
        url_name = "admin:auth:index"

        self.assertLoginRequired(url_name)

        with self.login(self.superuser):
            self.get(url_name)
            self.assert_http_302_found(url=self.reverse("admin:auth:users:list"))

    def test_user_list(self):
        self.get_generic_200(
            "admin:auth:users:list",
            self.superuser,
            ["model", "object_list"],
            self.shell.template("list.html"),
        )

    def test_user_list_shows_registration_and_last_login_dates(self):
        factories.UserFactory.create(
            username="veteran",
            date_joined=datetime(2018, 7, 10, 12, 0, tzinfo=timezone.utc),
            last_login=datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc),
        )
        factories.UserFactory.create(
            username="lurker",
            date_joined=datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc),
            last_login=None,
        )

        with self.login(self.superuser):
            self.get("admin:auth:users:list")
            self.assert_http_200_ok()
            for fragment in self.by_shell(
                workbook=(
                    '<th scope="col" class="wb-hide-narrow">Registered</th>',
                    '<th scope="col">Last login</th>',
                    '<td class="wb-hide-narrow" data-label="Registered">10 Jul 2018</td>',
                    '<td data-label="Last login">19 Sep 2026</td>',
                    '<td class="wb-hide-narrow" data-label="Registered">3 Sep 2026</td>',
                    '<td data-label="Last login">Never</td>',
                ),
                explorer=(
                    '<th class="wide-only">Registered</th>',
                    "<th>Last login</th>",
                    '<td class="wide-only">10 Jul 2018</td>',
                    "<td>19 Sep 2026</td>",
                    '<td class="wide-only">3 Sep 2026</td>',
                    "<td>Never</td>",
                ),
            ):
                self.assertResponseContains(fragment)

    def test_user_create(self):
        self.get_generic_200(
            "admin:auth:users:add",
            self.superuser,
            ["model", "form"],
            self.shell.template("edit.html"),
        )

    def test_user_edit(self):
        self.get_generic_200(
            "admin:auth:users:edit",
            self.superuser,
            ["model", "form", "object"],
            self.shell.template("edit.html"),
            pk=1,
        )

    def test_user_perms(self):
        self.get_generic_200(
            "admin:auth:users:perms",
            self.superuser,
            ["model", "formset"],
            self.shell.template("permissions.html"),
            pk=1,
        )

    def test_user_delete(self):
        url_name = "admin:auth:users:delete"

        with self.login(self.superuser):
            self.get(url_name, pk=1)
            self.assert_http_405_method_not_allowed()

            self.post(url_name, pk=1)
            self.assert_http_302_found(url=self.reverse("admin:auth:users:list"))


@per_shell
class AuthSiteGroupTests(TestCase):
    def setUp(self):
        super().setUp()
        self.group_instance = Group.objects.create(name="Group")

    def test_group_list(self):
        self.get_generic_200(
            "admin:auth:groups:list",
            self.superuser,
            ["model", "object_list"],
            self.shell.template("list.html"),
        )

    def test_group_create(self):
        self.get_generic_200(
            "admin:auth:groups:add",
            self.superuser,
            ["model", "form"],
            self.shell.template("edit.html"),
        )

    def test_group_edit(self):
        self.get_generic_200(
            "admin:auth:groups:edit",
            self.superuser,
            ["model", "form", "object"],
            self.shell.template("edit.html"),
            pk=self.group_instance.pk,
        )

    def test_group_perms(self):
        self.get_generic_200(
            "admin:auth:groups:perms",
            self.superuser,
            ["model", "formset"],
            self.shell.template("permissions.html"),
            pk=self.group_instance.pk,
        )

    def test_group_delete(self):
        url_name = "admin:auth:groups:delete"

        with self.login(self.superuser):
            self.get(url_name, pk=self.group_instance.pk)
            self.assert_http_405_method_not_allowed()

            self.post(url_name, pk=self.group_instance.pk)
            self.assert_http_302_found(url=self.reverse("admin:auth:groups:list"))


def lazy_twice(get_response):
    """Middleware that wraps ``request.user`` in a second lazy object."""

    def middleware(request):
        signed_in = request.user
        request.user = SimpleLazyObject(lambda: signed_in)
        return get_response(request)

    return middleware


class UserAdminUrls(AdminUrlMixin):
    """What a user model with admin pages of its own takes from the admin."""

    def _get_admin_namespace(self):
        return "admin:auth:users"

    def _get_url_args(self):
        return (self.pk,)

    def _get_url_names(self):
        return ["edit", "delete", "perms"]


@per_shell
class OwnUserRecordTests(TestCase):
    """
    Where the user model has admin pages (``AdminUrlMixin``), a user's own
    record is one of them. ``request.user`` is a lazy object that passes
    ``isinstance`` for the user model and is the ``user`` of every page's
    context, but the page's place is the page's own object, which is the real
    record.
    """

    def setUp(self):
        super().setUp()
        user_model = get_user_model()
        self.addCleanup(setattr, user_model, "__bases__", user_model.__bases__)
        user_model.__bases__ = (UserAdminUrls, *user_model.__bases__)
        # What the admin has remembered of the models with pages was learnt
        # while the user model had none, and must not outlive this test.
        models_by_namespace.cache_clear()
        self.addCleanup(models_by_namespace.cache_clear)
        for cache in (Explorer._section_cache, Explorer._relation_cache):
            patcher = mock.patch.dict(cache, clear=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def assertPlacedAtTheUser(self, aria_current):
        """The explorer's tree has the user's own record, and the page is at it."""
        user = self.superuser
        url = self.reverse("admin:auth:users:edit", pk=user.pk)
        self.assertResponseContains(
            self.by_shell(
                workbook=(
                    f'<a class="wb-node-link" href="{url}" title="{user}" '
                    f'aria-current="{aria_current}"><svg class="wb-icon" '
                    'aria-hidden="true" focusable="false"><use href="/static/'
                    'touchtechnology/admin/workbook/icons.svg#user"></use></svg>'
                    f'<span class="wb-node-label">{user}</span></a>'
                ),
                explorer=(
                    f'<a class="node-link" href="{url}" '
                    f'aria-current="{aria_current}"><svg class="icon" '
                    'aria-hidden="true" focusable="false"><use href="/static/'
                    'touchtechnology/admin/explorer/img/icons.svg#user"></use></svg>'
                    f'<span class="node-label">{user}</span></a>'
                ),
            )
        )

    def test_the_edit_page(self):
        with self.login(self.superuser):
            self.get_check_200("admin:auth:users:edit", self.superuser.pk)
        self.assertPlacedAtTheUser("page")

    def test_the_permissions_page(self):
        with self.login(self.superuser):
            self.get_check_200("admin:auth:users:perms", self.superuser.pk)
        self.assertPlacedAtTheUser("location")

    def test_the_edit_page_when_the_user_is_wrapped_twice(self):
        middleware = [*settings.MIDDLEWARE, f"{__name__}.lazy_twice"]
        with self.settings(MIDDLEWARE=middleware), self.login(self.superuser):
            self.get_check_200("admin:auth:users:edit", self.superuser.pk)
        self.assertPlacedAtTheUser("page")
