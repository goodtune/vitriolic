from datetime import date

from test_plus import TestCase

from touchtechnology.admin.setup import Setup, Step
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.admin import competition_setup, season_setup
from tournamentcontrol.competition.tests import factories


class SetupTests(TestCase):
    def test_next_is_first_required_step_not_done(self):
        setup = Setup(
            "Set-up",
            [
                Step("One", True),
                Step("Two", False, optional=True),
                Step("Three", False),
                Step("Four", False),
            ],
        )
        self.assertEqual(setup.next_step.label, "Three")
        self.assertEqual((setup.done, setup.total, setup.percent), (1, 3, 33))
        self.assertIs(setup.complete, False)

    def test_complete_ignores_optional_steps(self):
        setup = Setup("Set-up", [Step("One", True), Step("Two", False, optional=True)])
        self.assertIs(setup.complete, True)
        self.assertIsNone(setup.next_step)

    def test_folded_when_every_required_step_is_done(self):
        cases = [
            ("every step done", [Step("One", True), Step("Two", True)], True),
            ("a step to do", [Step("One", True), Step("Two", False)], False),
            (
                "only an optional step left",
                [Step("One", True), Step("Two", False, optional=True)],
                True,
            ),
        ]
        for name, steps, folded in cases:
            with self.subTest(name):
                self.assertEqual(Setup("Set-up", steps).folded, folded)


@per_shell(shells=("explorer",))
class SeasonSetupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        cls.season = factories.SeasonFactory.create(start_date=date(2026, 7, 8))
        cls.division = factories.DivisionFactory.create(season=cls.season)
        cls.stage = factories.StageFactory.create(division=cls.division)
        cls.pool = factories.StageGroupFactory.create(stage=cls.stage)

    def steps(self, season):
        return {step.label: step for step in season_setup(season).steps}

    def test_empty_season_points_at_time_slots(self):
        setup = season_setup(self.season)
        self.assertEqual(setup.next_step.label, "Add the kick-off times")
        self.assertEqual(
            setup.next_step.url, f"{self.season.urls['edit']}#timeslots-tab"
        )

    def test_division_short_of_teams_links_to_its_teams(self):
        step = self.steps(self.season)["Enter the teams"]
        self.assertIs(step.done, False)
        self.assertEqual(step.url, f"{self.division.urls['edit']}#teams-tab")

    def test_venue_without_grounds_links_to_its_grounds(self):
        venue = factories.VenueFactory.create(season=self.season)
        step = self.steps(self.season)["Add venues and their grounds"]
        self.assertIs(step.done, False)
        self.assertEqual(step.url, f"{venue.urls['edit']}#grounds-tab")
        factories.GroundFactory.create(venue=venue)
        self.assertIs(
            self.steps(self.season)["Add venues and their grounds"].done, True
        )

    def test_draw_built_and_scheduled(self):
        for _ in range(2):
            factories.TeamFactory.create(division=self.division)
        match = factories.MatchFactory.create(stage=self.stage, date=date(2026, 7, 8))
        steps = self.steps(self.season)
        self.assertIs(steps["Enter the teams"].done, True)
        self.assertIs(steps["Build the draw"].done, True)
        schedule = steps["Give every match a time and a ground"]
        self.assertIs(schedule.done, False)
        self.assertEqual(
            schedule.url,
            self.reverse(
                "admin:fixja:match-schedule",
                self.season.competition_id,
                self.season.pk,
                "20260708",
            ),
        )
        self.assertIsNone(match.play_at)

    def test_season_edit_shows_checklist(self):
        edit = self.season.url_names["edit"]
        with self.login(self.superuser):
            self.assertGoodView(edit.url_name, *edit.args)
        self.assertResponseContains(
            '<a class="tab" role="tab" id="setup-tab-link" href="#setup-tab" '
            'aria-controls="setup-tab" aria-selected="false" tabindex="-1">'
            '<svg class="icon" aria-hidden="true" focusable="false">'
            '<use href="/static/touchtechnology/admin/explorer/img/icons.svg#check"></use>'
            "</svg><span>Set-up</span>"
            '<span class="count" aria-hidden="true">3/8</span></a>'
        )
        self.assertResponseContains(
            f'<p class="setup-label"><a href="{self.season.urls["edit"]}#timeslots-tab">'
            "Add the kick-off times</a></p>"
        )

    def test_pool_edit_shows_season_progress(self):
        edit = self.pool.url_names["edit"]
        with self.login(self.superuser):
            self.assertGoodView(edit.url_name, *edit.args)
        self.assertResponseContains(
            f'<a href="{self.season.urls["edit"]}#setup-tab">'
            "<strong>Season set-up</strong> 3 of 8 done</a>"
        )
        self.assertIs(self.context["setup"].here, False)

    def test_competition_setup_asks_for_a_season(self):
        competition = factories.CompetitionFactory.create()
        setup = competition_setup(competition)
        self.assertEqual(
            [s.label for s in setup.steps if not s.done and not s.optional],
            ["Take in the clubs", "Add a season"],
        )
