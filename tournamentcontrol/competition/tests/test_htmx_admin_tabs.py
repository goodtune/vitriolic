import datetime
import uuid
from unittest.mock import patch

import cloudinary
from django.test import override_settings
from django.urls import reverse
from test_plus import TestCase

from touchtechnology.admin.sites import site
from touchtechnology.admin.tests.lists import unordered_pages_fail
from touchtechnology.admin.tests.shells import by_shell, per_shell
from touchtechnology.common.tests.factories import SuperUserFactory, UserFactory
from tournamentcontrol.competition.models import MatchScoreSheet
from tournamentcontrol.competition.tests import factories


class HtmxCompetitionTabTests(TestCase):
    """Tests for HTMX tab content loading on competition admin views."""

    @classmethod
    def setUpTestData(cls):
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
            self.assert_http_200_ok()
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
            self.assert_http_200_ok()
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
            self.assert_http_200_ok()
            self.assertResponseTemplateUsed(site.shell.template("_htmx_tab_empty.html"))

    def test_competition_htmx_tab_ignored_without_flag(self):
        """HTMX tab parameter is ignored when feature flag is off."""
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:edit",
                self.competition.pk,
                data={"_htmx_tab": "season_set"},
                extra={"HTTP_HX_REQUEST": "true"},
            )
            self.assert_http_200_ok()
            self.assertResponseTemplateUsed(site.shell.template("edit.html"))

    @override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
    def test_competition_htmx_tab_requires_htmx_header(self):
        """Tab parameter without HTMX header returns full page."""
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:edit",
                self.competition.pk,
                data={"_htmx_tab": "season_set"},
            )
            self.assert_http_200_ok()
            self.assertResponseTemplateUsed(site.shell.template("edit.html"))


class HtmxSeasonTabTests(TestCase):
    """Tests for HTMX tab content loading on season admin views."""

    @classmethod
    def setUpTestData(cls):
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
            self.assert_http_200_ok()
            self.assertResponseTemplateNotUsed(site.shell.template("edit.html"))

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
            self.assert_http_200_ok()
            self.assertResponseTemplateNotUsed(site.shell.template("edit.html"))

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
            self.assert_http_200_ok()
            self.assertResponseTemplateNotUsed(site.shell.template("edit.html"))

    def test_season_edit_traditional_mode(self):
        """Season edit page loads normally without HTMX flag."""
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:season:edit",
                self.competition.pk,
                self.season.pk,
            )
            self.assert_http_200_ok()
            self.assertInContext("form")
            self.assertInContext("object")

    @override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
    def test_season_htmx_tab_requires_auth(self):
        """HTMX tab requests require authentication."""
        args = (self.competition.pk, self.season.pk)
        self.get(
            "admin:fixja:competition:season:edit",
            *args,
            data={"_htmx_tab": "divisions"},
            extra={"HTTP_HX_REQUEST": "true"},
        )
        self.assert_http_302_found()
        tab = reverse(
            "admin:fixja:competition:season:edit",
            args=args,
            query={"_htmx_tab": "divisions"},
        )
        # The login view quotes "next" with "/" left bare, so compare the
        # URLs by their parsed query rather than as strings.
        self.assertURLEqual(
            self.last_response.url, reverse("admin:login", query={"next": tab})
        )


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
        return by_shell(
            workbook=f'<a href="{url}">{member}</a>',
            explorer=(
                f'<a href="{url}">'
                '<svg class="icon" aria-hidden="true" focusable="false">'
                '<use href="/static/touchtechnology/admin/explorer/img/icons.svg#person">'
                f"</use></svg><span>{member}</span></a>"
            ),
        )

    def _get_club_tab(self, **data):
        with self.login(self.superuser):
            self.get(
                "admin:fixja:club:edit",
                self.club.pk,
                data={"_htmx_tab": "members", **data},
                extra={"HTTP_HX_REQUEST": "true"},
            )
        self.assert_http_200_ok()

    def test_first_page_of_members(self):
        self._get_club_tab()
        self.assertResponseContains(self._member_link(self.members[0]))
        self.assertResponseContains(self._member_link(self.members[1]))
        self.assertResponseNotContains(self._member_link(self.members[2]))

    def test_second_page_of_members(self):
        self._get_club_tab(page=2)
        self.assertResponseContains(self._member_link(self.members[2]))
        self.assertResponseContains(self._member_link(self.members[3]))
        self.assertResponseNotContains(self._member_link(self.members[1]))

    def test_page_beyond_the_last_is_the_last(self):
        self._get_club_tab(page=99)
        self.assertResponseContains(self._member_link(self.members[4]))
        self.assertResponseNotContains(self._member_link(self.members[3]))

    def test_members_link_to_the_other_pages_of_the_tab(self):
        self._get_club_tab()
        for number in (2, 3):
            href = f"?_htmx_tab=members&page={number}"
            self.assertResponseContains(
                by_shell(
                    workbook=(
                        f'<a href="{href}" hx-get="{href}" hx-target="#members-pane" '
                        f'hx-swap="innerHTML" hx-push-url="false" '
                        f'aria-label="Page {number}">{number}</a>'
                    ),
                    explorer=(
                        f'<a href="{href}" hx-get="{href}" hx-target="#members-tab" '
                        f'hx-swap="innerHTML" hx-push-url="false">{number}</a>'
                    ),
                ),
            )

    def test_only_the_links_to_other_pages_replace_the_tab_pane(self):
        """
        The link to a member, or anything else in the list, leaves the page as
        it would anywhere else; boosting it loaded the page it leads to into the
        tab pane.
        """
        self._get_club_tab()
        self.assertResponseNotContains("hx-boost")
        self.assertResponseContains(self._member_link(self.members[0]))

    def test_pages_are_not_pushed_onto_the_history(self):
        "The pages of a tab are not recorded in the history."
        self._get_club_tab()
        self.assertResponseHeaders({"HX-Push-Url": "false"})

    def test_queryset_tab_is_paginated(self):
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:season:edit",
                self.season.competition.pk,
                self.season.pk,
                data={"_htmx_tab": "divisions", "page": 2},
                extra={"HTTP_HX_REQUEST": "true"},
            )
        self.assert_http_200_ok()
        self.assertEqual(len(self.get_context("object_list")), 1)
        self.assertEqual(self.get_context("paginator").count, 3)
        self.assertEqual(self.get_context("page"), 2)

    def test_page_size_is_a_setting(self):
        with override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TAB_PAGINATE_BY=4):
            self._get_club_tab()
        self.assertEqual(len(self.get_context("object_list")), 4)


class HtmxTabAddLinkTests(TestCase):
    """
    A related tab offers a link to add another of its objects, whichever the
    tab mode.
    """

    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        cls.club = factories.ClubFactory.create()
        factories.PersonFactory.create(club=cls.club)
        cls.season = factories.SeasonFactory.create()
        factories.DivisionFactory.create(season=cls.season)

    def _add_link(self, url_name, *args, type_name):
        url = reverse(url_name, args=args)
        return by_shell(
            workbook=(
                f'<a class="wb-button wb-button-primary wb-button-small" href="{url}">'
                '<svg class="wb-icon" aria-hidden="true" focusable="false">'
                '<use href="/static/touchtechnology/admin/workbook/icons.svg#plus"></use>'
                f"</svg>Add {type_name}</a>"
            ),
            explorer=(
                f'<a class="button primary compact" href="{url}">'
                '<svg class="icon" aria-hidden="true" focusable="false">'
                '<use href="/static/touchtechnology/admin/explorer/img/icons.svg#plus">'
                f"</use></svg><span>Add {type_name}</span></a>"
            ),
        )

    def test_club_people_tab_traditional_mode(self):
        with self.login(self.superuser):
            self.get("admin:fixja:club:edit", self.club.pk)
        self.assert_http_200_ok()
        self.assertResponseContains(
            self._add_link(
                "admin:fixja:club:person:add", self.club.pk, type_name="person"
            ),
        )

    @override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
    def test_club_people_tab_htmx_mode(self):
        with self.login(self.superuser):
            self.get(
                "admin:fixja:club:edit",
                self.club.pk,
                data={"_htmx_tab": "members"},
                extra={"HTTP_HX_REQUEST": "true"},
            )
        self.assert_http_200_ok()
        self.assertResponseContains(
            self._add_link(
                "admin:fixja:club:person:add", self.club.pk, type_name="person"
            ),
        )

    @override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
    def test_season_divisions_tab_htmx_mode(self):
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:season:edit",
                self.season.competition.pk,
                self.season.pk,
                data={"_htmx_tab": "divisions"},
                extra={"HTTP_HX_REQUEST": "true"},
            )
        self.assert_http_200_ok()
        self.assertResponseContains(
            self._add_link(
                "admin:fixja:competition:season:division:add",
                self.season.competition.pk,
                self.season.pk,
                type_name="division",
            ),
        )


@per_shell
@override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
class HtmxTabOrderTests(TestCase):
    """
    A tab fetched on its own shows a page of its objects at a time, so it lists
    them in a settled order.
    """

    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        cls.superuser = cls.make_user("superuser")

    def get_tab(self, obj, tab):
        edit = obj.url_names["edit"]
        with unordered_pages_fail(), self.login(self.superuser):
            self.get(
                edit.url_name,
                *edit.args,
                data={"_htmx_tab": tab},
                extra={"HTTP_HX_REQUEST": "true"},
            )
        self.assert_http_200_ok()

    def test_a_season_lists_its_time_slots_by_first_kick_off(self):
        season = factories.SeasonFactory.create()
        evening = factories.SeasonMatchTimeFactory.create(
            season=season, start=datetime.time(18), interval=40, count=3
        )
        morning = factories.SeasonMatchTimeFactory.create(
            season=season, start=datetime.time(9), interval=30, count=4
        )
        midday = factories.SeasonMatchTimeFactory.create(
            season=season, start=datetime.time(12, 30), interval=30, count=2
        )
        self.get_tab(season, "timeslots")
        self.assertEqual(
            list(self.get_context("object_list")), [morning, midday, evening]
        )

    def test_a_division_lists_its_exclusion_dates_by_date(self):
        division = factories.DivisionFactory.create()
        queens_birthday = factories.DivisionExclusionDateFactory.create(
            division=division, date=datetime.date(2026, 6, 8)
        )
        anzac_day = factories.DivisionExclusionDateFactory.create(
            division=division, date=datetime.date(2026, 4, 25)
        )
        labour_day = factories.DivisionExclusionDateFactory.create(
            division=division, date=datetime.date(2026, 5, 4)
        )
        self.get_tab(division, "exclusions")
        self.assertEqual(
            list(self.get_context("object_list")),
            [anzac_day, labour_day, queens_birthday],
        )

    def test_a_match_lists_its_ladder_entries_home_team_first(self):
        # A result gives the match a ladder entry for each team, home first.
        match = factories.MatchFactory.create(home_team_score=4, away_team_score=2)
        home = match.ladder_entries.get(team=match.home_team)
        away = match.ladder_entries.get(team=match.away_team)
        self.get_tab(match, "ladder_entries")
        self.assertEqual(list(self.get_context("object_list")), [home, away])

    @patch.multiple(
        cloudinary.config(),
        create=True,
        cloud_name="test",
        api_key="test",
        api_secret="test",
    )
    def test_a_match_lists_its_score_sheets_by_key(self):
        # A score sheet records nothing a person would order it by, such as when
        # it was uploaded; it is listed by its key, which settles the order.
        match = factories.MatchFactory.create()
        second = MatchScoreSheet.objects.create(
            uuid=uuid.UUID(int=2), match=match, image="harness/second"
        )
        first = MatchScoreSheet.objects.create(
            uuid=uuid.UUID(int=1), match=match, image="harness/first"
        )
        self.get_tab(match, "scoresheets")
        self.assertEqual(list(self.get_context("object_list")), [first, second])
