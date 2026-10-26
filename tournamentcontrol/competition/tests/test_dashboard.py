import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from test_plus import TestCase

from touchtechnology.admin.sites import site
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.admin.tests.test_menu import COMPONENTS, MenuMixin
from touchtechnology.common.tests.factories import (
    StaffFactory,
    SuperUserFactory,
    UserFactory,
)
from tournamentcontrol.competition.admin import CompetitionAdminComponent
from tournamentcontrol.competition.dashboard import (
    matches_progression_possible,
    matches_require_basic_results,
    matches_require_details_results,
    matches_require_progression,
    stages_require_progression,
)
from tournamentcontrol.competition.tests.factories import (
    MatchFactory,
    StageFactory,
    TeamFactory,
    UndecidedTeamFactory,
)

#: The widgets the competition puts on the admin's home page: the title of
#: each, and its icon in the Workbook and the Explorer.
WIDGETS = (
    ("Awaiting Scores", "list-checks", "results"),
    ("Progress Teams", "layers", "stage"),
    ("Season Reports", "printer", "print"),
    ("Awaiting Detailed Results", "chart-bar", "chart"),
    ("Awaiting MVP Points", "chart-bar", "chart"),
)


class OpenCompetitionAdminComponent(CompetitionAdminComponent):
    """
    The competition's component without its protection, for a test to
    register: the menu shows it to every member of staff. It links to the
    competition's pages, as the site's addresses were settled before the test
    runs.
    """

    unprotected = True


def match_awaiting_details():
    """
    A match with a result in a season that records statistics, and no detailed
    result yet: the one match Awaiting Detailed Results has to show.
    """
    return MatchFactory.create(
        home_team_score=5,
        away_team_score=3,
        stage__division__season__statistics=True,
    )


def knockout(stage, kick_off, final_kick_off):
    """
    Two semi finals in ``stage`` and a final between their winners, as a
    division whose only stage is its finals is drawn.
    """
    t1, t2, t3, t4 = TeamFactory.create_batch(4, division=stage.division)
    semi_1 = MatchFactory.create(
        stage=stage, home_team=t1, away_team=t4, datetime=kick_off, label="Semi 1"
    )
    semi_2 = MatchFactory.create(
        stage=stage, home_team=t2, away_team=t3, datetime=kick_off, label="Semi 2"
    )
    final = MatchFactory.create(
        stage=stage,
        home_team=None,
        away_team=None,
        home_team_eval="W",
        home_team_eval_related=semi_1,
        away_team_eval="W",
        away_team_eval_related=semi_2,
        datetime=final_kick_off,
        label="Final",
    )
    return semi_1, semi_2, final


class BasicResultTests(TestCase):
    @freeze_time("2019-07-15 09:00 UTC")
    def test_bare_all_in_utc(self):
        match = MatchFactory.create(
            datetime=datetime.datetime(2019, 7, 15, 8, 30, tzinfo=ZoneInfo("UTC")),
            stage__division__season__timezone="UTC",
        )
        self.assertCountEqual(matches_require_basic_results(), [match])

    @freeze_time("2019-07-15 09:00 +13")
    def test_bare_match_in_samoa(self):
        tzname = "Pacific/Apia"
        tzinfo = ZoneInfo(tzname)
        match = MatchFactory.create(
            datetime=timezone.make_aware(datetime.datetime(2019, 7, 15, 8, 30), tzinfo),
            stage__division__season__timezone=tzname,
        )
        self.assertCountEqual(matches_require_basic_results(), [match])

    @freeze_time("2019-07-15 09:00 +13")
    def test_bare_match_in_samoa_bye(self):
        tzname = "Pacific/Apia"
        tzinfo = ZoneInfo(tzname)
        match = MatchFactory.create(
            round=1,
            is_bye=True,
            away_team=None,
            datetime=None,
            date=datetime.date(2019, 7, 15),
            time=None,
            stage__division__season__timezone=tzname,
        )
        # A bye's would never exist in isolation.
        MatchFactory.create(
            round=1,
            datetime=timezone.make_aware(datetime.datetime(2019, 7, 15, 8, 30), tzinfo),
            stage=match.stage,
            home_team_score=5,
            away_team_score=4,
        )
        self.assertCountEqual(matches_require_basic_results(), [match])

    @freeze_time("2019-07-15 09:00 UTC")
    def test_upstream_match_excluded(self):
        kickoff = datetime.datetime(2019, 7, 15, 8, 30, tzinfo=ZoneInfo("UTC"))
        match = MatchFactory.create(
            datetime=kickoff, stage__division__season__timezone="UTC"
        )
        # Its result comes from the upstream provider, so it is never awaiting entry.
        MatchFactory.create(datetime=kickoff, stage=match.stage, upstream_id="mysideline:12345")
        self.assertCountEqual(matches_require_basic_results(), [match])


class DetailResultTests(TestCase):
    def test_upstream_match_excluded(self):
        match = MatchFactory.create(
            home_team_score=5,
            away_team_score=3,
            stage__division__season__statistics=True,
        )
        # Its detailed result comes from the upstream provider, so it is never awaiting
        # entry here, whatever the season's statistics setting.
        MatchFactory.create(
            stage=match.stage,
            home_team_score=4,
            away_team_score=2,
            upstream_id="mysideline:12345",
        )
        self.assertCountEqual(matches_require_details_results(), [match])


@freeze_time("2019-07-15 09:30 UTC")
class RequireProgression(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def assertProgression(
        self,
        test_stage,
        result_required_expected,
        require_progression_expected,
        possible_progression_expected,
        stage_progression_expected,
    ):
        with self.subTest(matches_require_basic_results=test_stage):
            res = matches_require_basic_results()
            self.assertCountEqual(
                res.values_list("home_team_title", "away_team_title"),
                result_required_expected,
            )
        with self.subTest(matches_require_progression=test_stage):
            res = matches_require_progression()
            self.assertCountEqual(
                res.values_list("home_team_title", "away_team_title"),
                require_progression_expected,
            )
        with self.subTest(matches_progression_possible=test_stage):
            res = matches_progression_possible()
            self.assertCountEqual(res, possible_progression_expected)
        with self.subTest(stages_require_progression=test_stage):
            res = stages_require_progression()
            self.assertEqual(res, stage_progression_expected)

    def test_trivial(self):
        # Need two match times, one in the past and one in the future.
        dt1 = datetime.datetime(2019, 7, 15, 8, 30, tzinfo=ZoneInfo("UTC"))
        dt2 = datetime.datetime(2019, 7, 15, 10, 30, tzinfo=ZoneInfo("UTC"))

        # Create a stage with four teams to play each other and then progress
        # the winners to a final.
        rounds = StageFactory.create(division__season__timezone="UTC", order=1)
        finals = StageFactory.create(division=rounds.division, order=2)
        t1, t2, t3, t4 = TeamFactory.create_batch(4, division=finals.division)

        # Semi Final
        m1 = MatchFactory.create(
            stage=finals, home_team=t1, away_team=t4, datetime=dt1, label="Semi 1"
        )
        m2 = MatchFactory.create(
            stage=finals, home_team=t2, away_team=t3, datetime=dt1, label="Semi 2"
        )
        # Final
        m3 = MatchFactory.create(
            stage=finals,
            home_team=None,
            away_team=None,
            home_team_eval="W",
            home_team_eval_related=m1,
            away_team_eval="W",
            away_team_eval_related=m2,
            datetime=dt2,
            label="Final",
        )

        self.assertProgression(
            "setup",
            [(t1.title, t4.title), (t2.title, t3.title)],
            [("Winner Semi 1", "Winner Semi 2")],
            [],  # progress not possible, semi not played
            {},
        )

        # Home teams win both matches 4-3
        for match in [m1, m2]:
            match.home_team_score = 4
            match.away_team_score = 3
            match.save()

        self.assertProgression(
            "after semis",
            [],
            [("Winner Semi 1", "Winner Semi 2")],
            [m3],  # semi results entered
            {finals.division: {finals: [m3]}},  # stage needs progressing
        )

        m3.home_team, m3.away_team = m1.home_team, m2.home_team
        m3.save()

        self.assertProgression("before final", [], [], [], {})

    def test_first_stage_of_its_division(self):
        """
        A division whose first (here only) stage is a knockout: no stage comes
        before it to hold its progression back, so the final is ready once its
        semi finals have results.
        """
        dt1 = datetime.datetime(2019, 7, 15, 8, 30, tzinfo=ZoneInfo("UTC"))
        dt2 = datetime.datetime(2019, 7, 15, 10, 30, tzinfo=ZoneInfo("UTC"))
        finals = StageFactory.create(division__season__timezone="UTC", order=1)
        semi_1, semi_2, final = knockout(finals, dt1, dt2)

        self.assertProgression(
            "setup",
            [
                (semi_1.home_team.title, semi_1.away_team.title),
                (semi_2.home_team.title, semi_2.away_team.title),
            ],
            [("Winner Semi 1", "Winner Semi 2")],
            [],  # progress not possible, semi not played
            {},
        )

        for match in [semi_1, semi_2]:
            match.home_team_score = 4
            match.away_team_score = 3
            match.save()

        self.assertProgression(
            "after semis",
            [],
            [("Winner Semi 1", "Winner Semi 2")],
            [final],
            {finals.division: {finals: [final]}},
        )


@per_shell
@freeze_time("2019-07-15 09:30 UTC")
class FirstStageProgressionPageTests(TestCase):
    """
    The admin's home page, and the progression page its Progress Teams widget
    links to, for a stage that is the first of its division.
    """

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.stage = StageFactory.create(division__season__timezone="UTC", order=1)

    def progress_url(self):
        division = self.stage.division
        return reverse(
            "admin:fixja:competition:season:division:stage:progress",
            args=(
                division.season.competition_id,
                division.season_id,
                division.pk,
                self.stage.pk,
            ),
        )

    def test_home_page_offers_the_final_of_a_first_stage_knockout(self):
        kick_off = datetime.datetime(2019, 7, 15, 8, 30, tzinfo=ZoneInfo("UTC"))
        semi_1, semi_2, _final = knockout(self.stage, kick_off, kick_off)
        for match in [semi_1, semi_2]:
            match.home_team_score = 4
            match.away_team_score = 3
            match.save()

        with self.login(self.superuser):
            self.get_check_200("admin:index")
        self.assertResponseContains(
            f'<a href="{self.progress_url()}">{self.stage.title}</a>'
        )

    def test_undecided_teams_of_a_first_stage(self):
        undecided = UndecidedTeamFactory.create(stage=self.stage, label="Host")
        MatchFactory.create(
            stage=self.stage,
            home_team=None,
            home_team_undecided=undecided,
            datetime=datetime.datetime(2019, 7, 15, 10, 30, tzinfo=ZoneInfo("UTC")),
        )

        with self.login(self.superuser):
            self.get_check_200("admin:index")
            self.assertResponseContains(
                f'<a href="{self.progress_url()}">{self.stage.title}</a>'
            )
            # No stage comes before it, so there is no ladder beside the
            # places to fill.
            self.get(self.progress_url())
            self.response_200()
            self.assertEqual(self.get_context("ladders"), {})

    def test_undecided_team_named_by_a_position_in_a_first_stage(self):
        """
        A place named by a position (G1P2) refers to the stage before, which a
        first stage does not have: the place is shown as written, and any team
        of the division may fill it.
        """
        home, away = TeamFactory.create_batch(2, division=self.stage.division)
        MatchFactory.create(
            stage=self.stage,
            home_team=None,
            home_team_undecided=UndecidedTeamFactory.create(
                stage=self.stage, formula="G1P2", label=""
            ),
            away_team=away,
            datetime=datetime.datetime(2019, 7, 15, 10, 30, tzinfo=ZoneInfo("UTC")),
        )

        with self.login(self.superuser):
            self.get(self.progress_url())
        self.response_200()
        (form,) = self.get_context("formset").forms
        self.assertEqual(form.instance.title, "G1P2")
        self.assertCountEqual(form.fields["team"].queryset, [home, away])

    def test_a_failing_widget_is_left_out_of_the_home_page(self):
        """
        The home page stands when one of its widgets fails: the widget is left
        out and the failure is logged.
        """
        with (
            self.login(self.superuser),
            patch(
                "tournamentcontrol.competition.dashboard.stages_require_progression",
                side_effect=RuntimeError("progression failed"),
            ),
            self.assertLogs("touchtechnology.common.templatetags.dashboard") as logs,
        ):
            self.get_check_200("admin:index")
        (record,) = logs.records
        self.assertEqual(
            record.getMessage(),
            "The dashboard widget 'Progress Teams' failed and was left out of "
            "the page.",
        )
        self.assertEqual(record.exc_info[0], RuntimeError)


class HomePageMixin(MenuMixin):
    def widget_headings(self, *titles):
        """
        The heading of each of the competition's widgets, or of those named by
        ``titles``, as the shell draws it.
        """
        return [
            f"<h2>{self.icon(self.by_shell(workbook=workbook, explorer=explorer))}"
            f"{title}</h2>"
            for title, workbook, explorer in WIDGETS
            if not titles or title in titles
        ]

    def assertWidgetsShown(self, *titles):
        """The home page shows each of the competition's widgets (or ``titles``), once."""
        for heading in self.widget_headings(*titles):
            with self.subTest(shown=heading):
                self.assertResponseContains(heading, count=1)

    def assertWidgetsHidden(self, *titles):
        """The home page shows none of the competition's widgets (or ``titles``)."""
        for heading in self.widget_headings(*titles):
            with self.subTest(hidden=heading):
                self.assertResponseNotContains(heading)


@per_shell
class SuperuserHomePageTests(HomePageMixin, TestCase):
    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        # Awaiting Detailed Results is drawn only while a match awaits one.
        match_awaiting_details()

    def test_every_widget_is_shown(self):
        self.assertMenu(self.make_user("superuser"), *COMPONENTS)
        self.assertWidgetsShown()


@per_shell
class StaffHomePageTests(HomePageMixin, TestCase):
    """
    The home page shows the competition's widgets to the people its menu shows
    the competition to, and to no one else.
    """

    user_factory = StaffFactory

    @classmethod
    def setUpTestData(cls):
        cls.staff = cls.make_user("staff")
        cls.organiser = cls.make_user("organiser", perms=["competition.change_match"])
        # Awaiting Detailed Results is drawn only while a match awaits one.
        match_awaiting_details()

    def test_a_permission_over_the_application(self):
        self.assertMenu(self.organiser, "content", "competition")
        self.assertWidgetsShown()

    def test_no_permission(self):
        self.assertMenu(self.staff, "content")
        self.assertWidgetsHidden()

    def test_an_unprotected_component(self):
        site.register(OpenCompetitionAdminComponent)
        self.addCleanup(site.unregister, OpenCompetitionAdminComponent)
        self.assertMenu(self.staff, "content", "competition")
        self.assertWidgetsShown()


@per_shell
class WidgetShowTests(HomePageMixin, TestCase):
    """
    The home page asks each widget whether it has anything to show
    (``DashboardWidget.show``) before it draws it. Awaiting Detailed Results is
    the one widget of the competition's that may say no: it is left out while
    no match awaits a detailed result, and drawn beside the others once one
    does. The others always say yes.
    """

    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        cls.superuser = cls.make_user("superuser")

    def home_page_queries(self):
        """
        What the home page costs a superuser while no match awaits a detailed
        result: the redirect lookup, the session, the user, one query for each
        of the four widgets that list something (Awaiting Scores, Progress
        Teams, Season Reports, Awaiting MVP Points) and a second for Progress
        Teams' stages, and one for Awaiting Detailed Results to ask whether it
        has anything to show; it is left out, so its list is never fetched.
        The other widgets answer ``show()`` without the database. Workbook
        spends two more on the page's jobs.
        """
        return self.by_shell(workbook=11, explorer=9)

    def get_home_page(self, queries):
        with self.login(self.superuser):
            # The first request fills the caches the site keeps from one
            # request to the next; measure the home page after that.
            self.get_check_200("admin:index")
            with self.assertNumQueries(queries):
                self.get_check_200("admin:index")

    def test_a_widget_with_nothing_to_show_is_left_out(self):
        self.get_home_page(self.home_page_queries())
        self.assertWidgetsHidden("Awaiting Detailed Results")
        self.assertWidgetsShown(
            "Awaiting Scores", "Progress Teams", "Season Reports", "Awaiting MVP Points"
        )

    def test_a_widget_with_something_to_show_is_drawn(self):
        match_awaiting_details()
        # One query more: the widget said it has a match, and then lists it.
        self.get_home_page(self.home_page_queries() + 1)
        self.assertWidgetsShown()
