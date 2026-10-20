"""
The console admin's ways around the hierarchy: the trail above each page, the
jump search, the season's match days, the division's ladder and the return
from a delete.
"""

import datetime

from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.models import Season
from tournamentcontrol.competition.tests import factories

ICONS = "/static/touchtechnology/admin/console/icons.svg"


class TrailTests(TestCase):
    """Every level above an object is a link on its page."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        cls.division = factories.DivisionFactory.create(
            title="Under Twelves",
            season__title="Winter Nights",
            season__competition__title="Lakeside Cup",
        )
        cls.season = cls.division.season
        cls.competition = cls.season.competition

    def test_division_page_trail_names_its_ancestors(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:competition:season:division:edit",
                *self.division._get_url_args(),
            )
        self.assertResponseContains(
            '<li><a href="/admin/"><span class="trail__label">Dashboard</span></a></li>',
            html=True,
        )
        self.assertResponseContains(
            '<li><a href="/admin/fixja/"><span class="trail__label">'
            "Tournament Control</span></a></li>",
            html=True,
        )
        self.assertResponseContains(
            f'<li><a href="{self.competition.urls["edit"]}">'
            '<span class="trail__kind">Competition</span>'
            '<span class="trail__label">Lakeside Cup</span></a></li>',
            html=True,
        )
        self.assertResponseContains(
            f'<li><a href="{self.season.urls["edit"]}">'
            '<span class="trail__kind">Season</span>'
            '<span class="trail__label">Winter Nights</span></a></li>',
            html=True,
        )

    def test_trail_uses_the_objects_the_view_loaded(self):
        """Naming the steps of the trail costs no queries of its own."""
        with self.login(self.superuser), self.assertNumQueriesLessThan(40):
            self.get(
                "admin:fixja:competition:season:division:edit",
                *self.division._get_url_args(),
            )
        self.response_200()

    def test_cancel_goes_up_a_level(self):
        """An existing object's Cancel leads to the page it is listed on."""
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:competition:season:edit", *self.season._get_url_args()
            )
        self.assertResponseContains(
            f'<a class="btn" href="{self.competition.urls["edit"]}">Cancel</a>',
            html=True,
        )


class JumpTests(TestCase):
    """The jump search finds an object of any kind by its name."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        cls.staff = UserFactory.create(is_staff=True)
        cls.season = factories.SeasonFactory.create(
            title="Marigold Summer", competition__title="Quayside League"
        )

    def test_anonymous_is_sent_to_sign_in(self):
        self.assertLoginRequired("admin:jump")

    def test_finds_a_season_with_where_it_is(self):
        with self.login(self.superuser):
            self.get_check_200("admin:jump", data={"q": "marigold"})
        self.assertResponseContains(
            f'<a class="jump__hit" role="option" href="{self.season.urls["edit"]}">'
            '<span class="jump__type">Season</span>'
            '<span class="jump__label">Marigold Summer</span>'
            '<span class="jump__context">Quayside League</span></a>',
            html=True,
        )
        self.assertTemplateUsed("touchtechnology/admin/jump.html")

    def test_every_word_must_match(self):
        with self.login(self.superuser):
            self.get_check_200("admin:jump", data={"q": "marigold winter"})
        self.assertEqual(self.get_context("found"), 0)

    def test_finds_the_places_of_the_menu(self):
        with self.login(self.superuser):
            self.get_check_200("admin:jump", data={"q": "draw format"})
        self.assertResponseContains(
            '<a class="jump__hit" role="option" href="/admin/fixja/draw-format/">'
            f'<svg class="i" aria-hidden="true" focusable="false"><use href="{ICONS}#i-chevron-right"></use></svg>'
            '<span class="jump__label">Draw Formats</span>'
            '<span class="jump__context">Tournament Control</span></a>',
            html=True,
        )

    def test_htmx_request_gets_the_results_alone(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:jump",
                data={"q": "marigold"},
                extra={"HTTP_HX_REQUEST": "true"},
            )
        self.assertTemplateUsed("touchtechnology/admin/_jump_results.html")
        self.assertTemplateNotUsed("touchtechnology/admin/base.html")

    def test_staff_without_permission_finds_nothing_of_the_model(self):
        with self.login(self.staff):
            self.get_check_200("admin:jump", data={"q": "marigold"})
        self.assertEqual(
            [kind for kind, hits in self.get_context("groups")],
            [],
        )


class MatchDayTests(TestCase):
    """The season page lists its match days and the work left on each."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        cls.season = factories.SeasonFactory.create()
        stage = factories.StageFactory.create(division__season=cls.season)
        cls.day = datetime.date(2026, 3, 4)
        factories.MatchFactory.create(
            stage=stage, date=cls.day, home_team_score=2, away_team_score=1
        )
        factories.MatchFactory.create(stage=stage, date=cls.day)

    def test_schedule_tab_links_to_the_day(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:competition:season:edit", *self.season._get_url_args()
            )
        url = self.reverse(
            "admin:fixja:match-results",
            self.season.competition.pk,
            self.season.pk,
            self.day.strftime("%Y%m%d"),
        )
        self.assertResponseContains(
            f'<a class="btn btn--sm" href="{url}">'
            f'<svg class="i" aria-hidden="true" focusable="false"><use href="{ICONS}#i-check"></use></svg>'
            '<span class="label">Results</span></a>',
            html=True,
        )
        self.assertResponseContains(
            '<span class="tag tag--warn">1 of 2</span>', html=True
        )


class LadderTabTests(TestCase):
    """The division page has a tab with its ladder."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        cls.division = factories.DivisionFactory.create()

    def test_empty_ladder_says_so(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:competition:season:division:edit",
                *self.division._get_url_args(),
            )
        self.assertResponseContains(
            '<a class="tab" role="tab" id="ladder-tab-label" href="#ladder-tab" '
            'aria-controls="ladder-tab" aria-selected="false">'
            f'<svg class="i" aria-hidden="true" focusable="false"><use href="{ICONS}#i-trophy"></use></svg>'
            "Ladder</a>",
            html=True,
        )
        self.assertResponseContains(
            '<p class="empty-state">No results yet: the ladder fills in as '
            "results are entered.</p>",
            html=True,
        )


class DeleteReturnTests(TestCase):
    """A delete goes back to the page it was asked from, when that is here."""

    def setUp(self):
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.season = factories.SeasonFactory.create()

    def test_next_on_this_site_is_followed(self):
        competition = self.season.competition
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:delete",
                *self.season._get_url_args(),
                data={"next": competition.urls["edit"] + "#seasons-tab"},
            )
        self.assertRedirects(
            self.last_response,
            competition.urls["edit"] + "#seasons-tab",
            fetch_redirect_response=False,
        )
        self.assertEqual(Season.objects.filter(pk=self.season.pk).count(), 0)

    def test_next_elsewhere_is_ignored(self):
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:delete",
                *self.season._get_url_args(),
                data={"next": "https://elsewhere.example/"},
            )
        self.assertRedirects(
            self.last_response,
            "/admin/fixja/competition/%d/seasons/" % self.season.competition_id,
            fetch_redirect_response=False,
        )
        self.assertEqual(Season.objects.filter(pk=self.season.pk).count(), 0)
