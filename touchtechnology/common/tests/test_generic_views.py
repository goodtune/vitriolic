import unittest

from django.contrib.auth.views import redirect_to_login
from django.test.utils import override_script_prefix, override_settings
from example_app.models import Relative, TestDateTimeField
from example_app.tests.factories import TestDateTimeFieldFactory
from test_plus import TestCase as BTC

from touchtechnology.common.tests import factories


# The example urlconf has no admin site to sign in to, only the accounts pages.
@override_settings(ROOT_URLCONF="example_app.urls", LOGIN_URL="accounts:login")
class TestCase(BTC):
    user_factory = factories.UserFactory

    @classmethod
    def setUpTestData(cls):
        cls.staff = cls.make_user("staff")
        cls.staff.is_staff = cls.staff.is_superuser = True
        cls.staff.save()
        cls.regular = cls.make_user("regular")


class GenericListTests(TestCase):
    def test_vanilla(self):
        self.assertGoodView("generic:vanilla:list")
        self.assertResponseContains("<title>test date time field</title>")
        self.assertResponseContains("<h1>test date time fields</h1>")

    def test_permissions_403(self):
        "Ensure unprivileged user is denied, superuser may view"
        self.assertLoginRequired("generic:permissions:list")

        with self.login(self.regular):
            self.get("generic:permissions:list")
            self.assert_http_403_forbidden()

        with self.login(self.staff):
            self.assertGoodView("generic:permissions:list")


class GenericDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        TestDateTimeFieldFactory.reset_sequence()
        TestDateTimeFieldFactory.create_batch(20)
        cls.instance = TestDateTimeField.objects.earliest("pk")

    def test_vanilla(self):
        self.assertGoodView("generic:vanilla:detail", self.instance.pk)
        self.assertResponseContains("<title>test date time field</title>")
        self.assertResponseContains("<h1>test date time fields</h1>")
        self.assertResponseContains(f"<p>{self.instance.datetime}</p>")

    @unittest.skip("permissions_required not implemented for generic_detail")
    def test_permissions_403(self):
        self.get("generic:permissions:detail", self.instance.pk)
        self.assert_http_403_forbidden()


class GenericEditTests(TestCase):
    def test_vanilla(self):
        self.assertGoodView("generic:vanilla:add")
        self.assertResponseContains("<title>Edit test date time field</title>")

        data = {
            "datetime_0": "2015-1-1",
            "datetime_1": "9:00",
            "datetime_2": "UTC",
        }
        self.post("generic:vanilla:add", data=data)
        self.assertEqual(1, TestDateTimeField.objects.count())
        self.assert_http_302_found(url=self.reverse("generic:vanilla:list"))

        self.assertGoodView("generic:vanilla:list")
        self.assertResponseContains("<li>2015-01-01 09:00:00+00:00</li>")

    def test_permissions_403(self):
        "Ensure unprivileged user is denied, superuser may view and edit"
        self.assertLoginRequired("generic:permissions:add")

        data = {
            "datetime_0": "2015-1-1",
            "datetime_1": "9:00",
            "datetime_2": "UTC",
        }

        with self.login(self.regular):
            self.get("generic:permissions:add")
            self.assert_http_403_forbidden()
            self.post("generic:permissions:add", data=data)
            self.assert_http_403_forbidden()

        with self.login(self.staff):
            self.assertGoodView("generic:permissions:add")
            self.post("generic:permissions:add", data=data)
            self.assert_http_302_found(url=self.reverse("generic:permissions:list"))


class GenericDeleteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.object = TestDateTimeFieldFactory.create()

    def test_vanilla(self):
        self.post("generic:vanilla:delete", self.object.pk)
        self.assert_http_302_found(url=self.reverse("generic:vanilla:list"))

    def test_permissions_403(self):
        "Ensure unprivileged user is denied, superuser may delete"
        delete_url = self.reverse("generic:permissions:delete", self.object.pk)
        # A POST, so assertLoginRequired (which uses GET) does not apply. The
        # URL comes from redirect_to_login: test-plus compares it as a string,
        # and reverse(query=) escapes the slashes in "next".
        self.post(delete_url)
        self.assert_http_302_found(url=redirect_to_login(delete_url).url)

        with self.login(self.regular):
            self.post(delete_url)
            self.assert_http_403_forbidden()

        with self.login(self.staff):
            self.post(delete_url)
            self.assert_http_302_found(url=self.reverse("generic:permissions:list"))


class GenericPermissionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.object = TestDateTimeFieldFactory.create()

    def test_vanilla(self):
        self.get("generic:vanilla:perms", self.object.pk)
        self.assert_http_403_forbidden()

        with self.login(self.regular):
            self.get("generic:vanilla:perms", self.object.pk)
            self.assert_http_403_forbidden()

        with self.login(self.staff):
            self.assertGoodView("generic:vanilla:perms", self.object.pk)
            self.assertResponseContains(f"""
                <p>
                    Control who <em>can change test date time field</em>
                    for the test date time field
                    <strong>{self.object}</strong>.
                </p>
            """)


class GenericEditMultipleTests(TestCase):
    def test_vanilla(self):
        self.assertGoodView("generic:vanilla:edit")
        self.assertResponseContains(
            "<title>Edit multiple test date time fields</title>"
        )

        data = {
            # management form hidden fields
            "form-TOTAL_FORMS": 2,
            "form-INITIAL_FORMS": 0,
            "form-MIN_NUM_FORMS": 0,
            "form-MAX_NUM_FORMS": 1000,
            "form-0-datetime_0": "2015-1-1",
            "form-0-datetime_1": "9:00",
            "form-0-datetime_2": "UTC",
            "form-1-datetime_0": "2016-3-3",
            "form-1-datetime_1": "9:00",
            "form-1-datetime_2": "UTC",
        }
        self.post("generic:vanilla:edit", data=data)
        self.assertEqual(2, TestDateTimeField.objects.count())
        self.assert_http_302_found(url=self.reverse("generic:vanilla:list"))

        self.assertGoodView("generic:vanilla:list")
        self.assertResponseContains(
            "<ul>"
            "<li>2015-01-01 09:00:00+00:00</li>"
            "<li>2016-03-03 09:00:00+00:00</li>"
            "</ul>"
        )

    def test_permissions_403(self):
        "Ensure unprivileged user is denied, superuser may view and edit"
        self.assertLoginRequired("generic:permissions:edit")

        data = {
            # management form hidden fields
            "form-TOTAL_FORMS": 2,
            "form-INITIAL_FORMS": 0,
            "form-MIN_NUM_FORMS": 0,
            "form-MAX_NUM_FORMS": 1000,
            "form-0-datetime_0": "2015-1-1",
            "form-0-datetime_1": "9:00",
            "form-0-datetime_2": "UTC",
            "form-1-datetime_0": "2016-3-3",
            "form-1-datetime_1": "9:00",
            "form-1-datetime_2": "UTC",
        }

        with self.login(self.regular):
            self.get("generic:permissions:edit")
            self.assert_http_403_forbidden()
            self.post("generic:permissions:edit", data=data)
            self.assert_http_403_forbidden()

        with self.login(self.staff):
            self.assertGoodView("generic:permissions:edit")
            self.post("generic:permissions:edit", data=data)
            self.assert_http_302_found(url=self.reverse("generic:permissions:list"))

        self.assertEqual(2, TestDateTimeField.objects.count())


class GenericBulkCreateTests(TestCase):
    def test_vanilla(self):
        self.assertGoodView("generic:vanilla:bulk_create")
        self.assertResponseContains("<title>Bulk create test date time fields</title>")

        # Test creating multiple objects with bulk create
        data = {
            # management form hidden fields (default extra=3)
            "form-TOTAL_FORMS": 3,
            "form-INITIAL_FORMS": 0,
            "form-MIN_NUM_FORMS": 0,
            "form-MAX_NUM_FORMS": 1000,
            "form-0-datetime_0": "2015-1-1",
            "form-0-datetime_1": "9:00",
            "form-0-datetime_2": "UTC",
            "form-1-datetime_0": "2016-3-3",
            "form-1-datetime_1": "10:00",
            "form-1-datetime_2": "UTC",
            # form-2 left empty to test partial submission
        }

        self.post("generic:vanilla:bulk_create", data=data)
        # Should create 2 objects (form-2 was empty)
        self.assert_http_302_found(url=self.reverse("generic:vanilla:list"))

        # Verify the objects were created correctly
        self.assertQuerySetEqual(
            TestDateTimeField.objects.order_by("datetime"),
            [
                "<TestDateTimeField: 2015-01-01 09:00:00+00:00>",
                "<TestDateTimeField: 2016-03-03 10:00:00+00:00>",
            ],
            transform=repr,
        )

    def test_permissions_403(self):
        "Ensure unprivileged user is denied, superuser may view and create"
        self.assertLoginRequired("generic:permissions:bulk_create")

        data = {
            # management form hidden fields
            "form-TOTAL_FORMS": 2,
            "form-INITIAL_FORMS": 0,
            "form-MIN_NUM_FORMS": 0,
            "form-MAX_NUM_FORMS": 1000,
            "form-0-datetime_0": "2015-1-1",
            "form-0-datetime_1": "9:00",
            "form-0-datetime_2": "UTC",
        }

        with self.login(self.regular):
            self.get("generic:permissions:bulk_create")
            self.assert_http_403_forbidden()
            self.post("generic:permissions:bulk_create", data=data)
            self.assert_http_403_forbidden()

        with self.login(self.staff):
            self.get_check_200("generic:permissions:bulk_create")
            self.post("generic:permissions:bulk_create", data=data)
            self.assert_http_302_found(url=self.reverse("generic:permissions:list"))

        # Verify that one object was created by the staff user
        self.assertQuerySetEqual(
            TestDateTimeField.objects.all(),
            ["<TestDateTimeField: 2015-01-01 09:00:00+00:00>"],
            transform=repr,
        )


class GenericNestedRedirectTests(TestCase):
    """
    The relatives of an object nest under it with no list of their own, so the
    generic views send them back to the nearest page above: the object's.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.parent = TestDateTimeFieldFactory.create()

    def test_adding_returns_to_the_parent(self):
        self.post("generic:vanilla:relative:add", self.parent.pk, data={"name": "Ann"})
        self.assert_http_302_found(
            url=self.reverse("generic:vanilla:detail", self.parent.pk)
        )
        self.get_check_200("generic:vanilla:detail", self.parent.pk)
        self.assertCountEqual(
            self.parent.relative_set.values_list("name", flat=True), ["Ann"]
        )

    def test_deleting_returns_to_the_parent(self):
        relative = Relative.objects.create(link=self.parent, name="Ann")
        self.post("generic:vanilla:relative:delete", self.parent.pk, relative.pk)
        self.assert_http_302_found(
            url=self.reverse("generic:vanilla:detail", self.parent.pk)
        )
        self.assertCountEqual(self.parent.relative_set.all(), [])

    def test_editing_several_returns_to_the_parent(self):
        relative = Relative.objects.create(link=self.parent, name="Ann")
        self.post(
            "generic:vanilla:relative:edit",
            self.parent.pk,
            data={
                "form-TOTAL_FORMS": 1,
                "form-INITIAL_FORMS": 1,
                "form-0-id": relative.pk,
                "form-0-name": "Bob",
            },
        )
        self.assert_http_302_found(
            url=self.reverse("generic:vanilla:detail", self.parent.pk)
        )
        self.assertCountEqual(
            self.parent.relative_set.values_list("name", flat=True), ["Bob"]
        )

    def test_creating_several_returns_to_the_parent(self):
        self.post(
            "generic:vanilla:relative:bulk_create",
            self.parent.pk,
            data={
                "form-TOTAL_FORMS": 1,
                "form-INITIAL_FORMS": 0,
                "form-0-name": "Ann",
                "form-0-link": self.parent.pk,
            },
        )
        self.assert_http_302_found(
            url=self.reverse("generic:vanilla:detail", self.parent.pk)
        )
        self.assertCountEqual(
            self.parent.relative_set.values_list("name", flat=True), ["Ann"]
        )

    def test_deleting_below_a_script_name_keeps_it(self):
        # The views are found without the script name; the browser needs it.
        relative = Relative.objects.create(link=self.parent, name="Ann")
        self.post(
            "generic:vanilla:relative:delete",
            self.parent.pk,
            relative.pk,
            extra={"SCRIPT_NAME": "/club"},
        )
        with override_script_prefix("/club/"):
            self.assert_http_302_found(
                url=self.reverse("generic:vanilla:detail", self.parent.pk)
            )
