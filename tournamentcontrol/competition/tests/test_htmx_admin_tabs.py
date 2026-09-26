from django.test import override_settings
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
