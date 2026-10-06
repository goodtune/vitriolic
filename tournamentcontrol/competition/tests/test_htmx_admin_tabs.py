from django.test import override_settings
from django.urls import reverse
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.tests import factories


class HtmxCompetitionTabTests(TestCase):
    """Tests for HTMX tab content loading on competition admin views."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.competition = factories.CompetitionFactory.create()
        cls.season = factories.SeasonFactory.create(
            competition=cls.competition,
        )

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def test_competition_edit_traditional_mode(self):
        """Competition edit page loads normally without HTMX flag."""
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:edit",
                self.competition.pk,
            )
            self.response_200()
            self.assertInContext("form")
            self.assertInContext("object")

    @override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
    def test_competition_edit_htmx_mode_full_page(self):
        """Competition edit page loads full page in HTMX mode (non-HTMX request)."""
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:edit",
                self.competition.pk,
            )
            self.response_200()
            self.assertInContext("form")
            self.assertInContext("object")

    @override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
    def test_competition_edit_htmx_tab_nonexistent(self):
        """HTMX request for a non-existent tab returns empty template."""
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:edit",
                self.competition.pk,
                data={"_htmx_tab": "nonexistent_tab"},
                extra={"HTTP_HX_REQUEST": "true"},
            )
            self.response_200()
            self.assertTemplateUsed(
                self.last_response,
                "touchtechnology/admin/_htmx_tab_empty.html",
            )

    def test_competition_htmx_tab_ignored_without_flag(self):
        """HTMX tab parameter is ignored when feature flag is off."""
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:edit",
                self.competition.pk,
                data={"_htmx_tab": "season_set"},
                extra={"HTTP_HX_REQUEST": "true"},
            )
            self.response_200()
            self.assertTemplateUsed(
                self.last_response, "touchtechnology/admin/edit.html"
            )

    @override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
    def test_competition_htmx_tab_requires_htmx_header(self):
        """Tab parameter without HTMX header returns full page."""
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:edit",
                self.competition.pk,
                data={"_htmx_tab": "season_set"},
            )
            self.response_200()
            self.assertTemplateUsed(
                self.last_response, "touchtechnology/admin/edit.html"
            )


class HtmxSeasonTabTests(TestCase):
    """Tests for HTMX tab content loading on season admin views."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = factories.SeasonFactory.create()
        cls.competition = cls.season.competition

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    @override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
    def test_season_edit_htmx_tab_divisions(self):
        """HTMX request for season divisions tab returns partial content."""
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:season:edit",
                self.competition.pk,
                self.season.pk,
                data={"_htmx_tab": "divisions"},
                extra={"HTTP_HX_REQUEST": "true"},
            )
            self.response_200()
            self.assertTemplateNotUsed(
                self.last_response, "touchtechnology/admin/edit.html"
            )

    @override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
    def test_season_edit_htmx_tab_venues(self):
        """HTMX request for season venues tab returns partial content."""
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:season:edit",
                self.competition.pk,
                self.season.pk,
                data={"_htmx_tab": "venues"},
                extra={"HTTP_HX_REQUEST": "true"},
            )
            self.response_200()
            self.assertTemplateNotUsed(
                self.last_response, "touchtechnology/admin/edit.html"
            )

    @override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
    def test_season_edit_htmx_tab_exclusions(self):
        """HTMX request for season exclusions tab returns partial content."""
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:season:edit",
                self.competition.pk,
                self.season.pk,
                data={"_htmx_tab": "exclusions"},
                extra={"HTTP_HX_REQUEST": "true"},
            )
            self.response_200()
            self.assertTemplateNotUsed(
                self.last_response, "touchtechnology/admin/edit.html"
            )

    def test_season_edit_traditional_mode(self):
        """Season edit page loads normally without HTMX flag."""
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:season:edit",
                self.competition.pk,
                self.season.pk,
            )
            self.response_200()
            self.assertInContext("form")
            self.assertInContext("object")

    @override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
    def test_season_htmx_tab_requires_auth(self):
        """HTMX tab requests require authentication."""
        self.get(
            "admin:fixja:competition:season:edit",
            self.competition.pk,
            self.season.pk,
            data={"_htmx_tab": "divisions"},
            extra={"HTTP_HX_REQUEST": "true"},
        )
        self.response_302()


@override_settings(
    TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True,
    TOUCHTECHNOLOGY_HTMX_ADMIN_TAB_PAGINATE_BY=2,
)
class HtmxTabPaginationTests(TestCase):
    """Related tabs show one page of their objects at a time."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        cls.club = factories.ClubFactory.create()
        # Not using the PersonFactory, the members are listed by last name.
        cls.members = [
            cls.club.members.create(first_name="Alice", last_name=f"Member{n}")
            for n in range(1, 6)
        ]
        cls.season = factories.SeasonFactory.create()
        cls.divisions = factories.DivisionFactory.create_batch(3, season=cls.season)

    def _member_link(self, member):
        url = reverse("admin:fixja:club:person:edit", args=[self.club.pk, member.pk])
        return f'<a href="{url}">{member}</a>'

    def _get_club_tab(self, **data):
        with self.login(self.superuser):
            self.get(
                "admin:fixja:club:edit",
                self.club.pk,
                data={"_htmx_tab": "members", **data},
                extra={"HTTP_HX_REQUEST": "true"},
            )
        self.response_200()

    def test_first_page_of_members(self):
        self._get_club_tab()
        self.assertResponseContains(self._member_link(self.members[0]), html=True)
        self.assertResponseContains(self._member_link(self.members[1]), html=True)
        self.assertResponseNotContains(self._member_link(self.members[2]), html=True)

    def test_second_page_of_members(self):
        self._get_club_tab(page=2)
        self.assertResponseContains(self._member_link(self.members[2]), html=True)
        self.assertResponseContains(self._member_link(self.members[3]), html=True)
        self.assertResponseNotContains(self._member_link(self.members[1]), html=True)

    def test_page_beyond_the_last_is_the_last(self):
        self._get_club_tab(page=99)
        self.assertResponseContains(self._member_link(self.members[4]), html=True)
        self.assertResponseNotContains(self._member_link(self.members[3]), html=True)

    def test_members_link_to_the_other_pages_of_the_tab(self):
        self._get_club_tab()
        for number in (2, 3):
            href = f"?_htmx_tab=members&page={number}"
            self.assertResponseContains(
                f'<a href="{href}" hx-get="{href}" hx-target="#members-tab" '
                f'hx-swap="innerHTML" hx-push-url="false">{number}</a>',
                html=True,
            )

    def test_only_the_links_to_other_pages_replace_the_tab_pane(self):
        """
        The link to a member, or anything else in the list, leaves the page as
        it would anywhere else; boosting it loaded the page it leads to into the
        tab pane.
        """
        self._get_club_tab()
        self.assertResponseNotContains("hx-boost")
        self.assertResponseContains(self._member_link(self.members[0]), html=True)

    def test_pages_are_not_pushed_onto_the_history(self):
        "The pages of a tab are not recorded in the history."
        self._get_club_tab()
        self.assertEqual(self.last_response["HX-Push-Url"], "false")

    def test_queryset_tab_is_paginated(self):
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:season:edit",
                self.season.competition.pk,
                self.season.pk,
                data={"_htmx_tab": "divisions", "page": 2},
                extra={"HTTP_HX_REQUEST": "true"},
            )
        self.response_200()
        self.assertEqual(len(self.get_context("object_list")), 1)
        self.assertEqual(self.get_context("paginator").count, 3)
        self.assertEqual(self.get_context("page"), 2)

    def test_page_size_is_a_setting(self):
        with override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TAB_PAGINATE_BY=4):
            self._get_club_tab()
        self.assertEqual(len(self.get_context("object_list")), 4)
