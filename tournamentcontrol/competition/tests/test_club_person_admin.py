"""
The pages of a club's people in the competition admin, served as a multi-tenant
installation serves them: each request has a ``tenant``.

The admin site hands every page of a component the site (``admin``) it is part
of, and a multi-tenant installation asks that site whether the component is
hidden for the tenant before it draws the page.
"""

from unittest import mock

from django.contrib import messages
from test_plus import TestCase

from touchtechnology.admin.sites import site
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.admin.tests.tenancy import as_tenant
from tournamentcontrol.competition.tests import factories


@per_shell
@as_tenant
class ClubPersonTests(TestCase):
    user_factory = factories.SuperUserFactory

    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.person = factories.PersonFactory.create(
            first_name="Alice", last_name="Walker"
        )
        self.club = self.person.club

    def data(self, **kwargs):
        return {
            "first_name": "Alice",
            "last_name": "Walker",
            "gender": "F",
            "date_of_birth": "1990-04-27",
            "email": "",
            "home_phone": "",
            "work_phone": "",
            "mobile_phone": "",
            "user": "",
            **kwargs,
        }

    def first_name_input(self, value=None):
        """The first name's field of the form, with ``value`` when there is one."""
        value = "" if value is None else f'value="{value}"'
        return self.by_shell(
            workbook=(
                f'<input type="text" name="first_name" {value} maxlength="50" '
                'class="wb-input" required id="id_first_name">'
            ),
            explorer=(
                f'<input type="text" name="first_name" {value} maxlength="50" '
                'required id="id_first_name">'
            ),
        )

    def test_add_person_page(self):
        with self.login(self.user):
            self.get_check_200("admin:fixja:club:person:add", self.club.pk)

        self.assertResponseContains("<h1>New person</h1>")
        self.assertResponseContains(self.first_name_input())

    def test_person_page_is_drawn_for_the_admin_site(self):
        with self.login(self.user):
            self.get_check_200("admin:fixja:club:person:add", self.club.pk)

        self.assertContext("admin", site)

    def test_person_page_of_a_component_hidden_for_the_tenant(self):
        with (
            mock.patch.object(site, "_hidden_component", return_value=True),
            self.login(self.user),
        ):
            self.get("admin:fixja:club:person:add", self.club.pk)

        self.assert_http_302_found(url=self.reverse("admin:index"))
        self.assertResponseMessages(
            [
                messages.Message(
                    messages.ERROR,
                    'Attempt to access component "Tournament Control" '
                    "is not allowed for this tenant.",
                )
            ]
        )

    def test_add_person(self):
        with self.login(self.user):
            self.post(
                "admin:fixja:club:person:add",
                self.club.pk,
                data=self.data(first_name="Beatrice", last_name="Newcomer"),
            )

        self.assert_http_302_found(
            url=self.reverse("admin:fixja:club:edit", self.club.pk)
        )
        self.assertEqual(
            self.club.members.get(last_name="Newcomer").first_name, "Beatrice"
        )

    def test_edit_person_page(self):
        with self.login(self.user):
            self.get_check_200(
                "admin:fixja:club:person:edit", self.club.pk, self.person.pk
            )

        self.assertResponseContains("<h1>Walker, Alice</h1>")
        self.assertResponseContains(self.first_name_input("Alice"))

    def test_edit_person(self):
        with self.login(self.user):
            self.post(
                "admin:fixja:club:person:edit",
                self.club.pk,
                self.person.pk,
                data=self.data(first_name="Alicia"),
            )

        self.assert_http_302_found(
            url=self.reverse("admin:fixja:club:edit", self.club.pk)
        )
        self.person.refresh_from_db()
        self.assertEqual(self.person.first_name, "Alicia")

    def test_edit_person_with_errors(self):
        with self.login(self.user):
            self.post(
                "admin:fixja:club:person:edit",
                self.club.pk,
                self.person.pk,
                data=self.data(first_name=""),
            )

        self.assert_http_200_ok()
        self.assertResponseContains(
            self.by_shell(
                workbook=(
                    '<p class="wb-error" id="id_first_name_error">'
                    '<svg class="wb-icon" aria-hidden="true" focusable="false">'
                    '<use href="/static/touchtechnology/admin/workbook/icons.svg'
                    '#circle-alert"></use></svg>'
                    "<span>This field is required.</span></p>"
                ),
                explorer="<li>This field is required.</li>",
            )
        )
        self.person.refresh_from_db()
        self.assertEqual(self.person.first_name, "Alice")

    def test_transfer_person_page(self):
        with self.login(self.user):
            self.get_check_200(
                "admin:fixja:club:person:transfer", self.club.pk, self.person.pk
            )

        self.assertResponseContains("<h1>Walker, Alice</h1>")

    def test_transfer_person(self):
        target = factories.ClubFactory.create()

        with self.login(self.user):
            self.post(
                "admin:fixja:club:person:transfer",
                self.club.pk,
                self.person.pk,
                data={"club": target.pk},
            )

        self.assert_http_302_found(
            url=self.reverse("admin:fixja:club:edit", self.club.pk)
        )
        self.person.refresh_from_db()
        self.assertEqual(self.person.club, target)

    def test_merge_person_page(self):
        with self.login(self.user):
            self.get_check_200(
                "admin:fixja:club:person:merge", self.club.pk, self.person.pk
            )

        self.assertResponseContains("<h1>Walker, Alice</h1>")
