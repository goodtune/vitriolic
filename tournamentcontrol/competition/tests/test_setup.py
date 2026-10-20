from datetime import date

from test_plus import TestCase

from touchtechnology.admin.setup import Setup, Step
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
        self.assertFalse(setup.complete)

    def test_complete_ignores_optional_steps(self):
        setup = Setup("Set-up", [Step("One", True), Step("Two", False, optional=True)])
        self.assertTrue(setup.complete)
        self.assertIsNone(setup.next_step)


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
            setup.next_step.url, "%s#timeslots-tab" % self.season.urls["edit"]
        )

    def test_division_short_of_teams_links_to_its_teams(self):
        step = self.steps(self.season)["Enter the teams"]
        self.assertFalse(step.done)
        self.assertEqual(step.url, "%s#teams-tab" % self.division.urls["edit"])

    def test_venue_without_grounds_links_to_its_grounds(self):
        venue = factories.VenueFactory.create(season=self.season)
        step = self.steps(self.season)["Add venues and their grounds"]
        self.assertFalse(step.done)
        self.assertEqual(step.url, "%s#grounds-tab" % venue.urls["edit"])
        factories.GroundFactory.create(venue=venue)
        self.assertTrue(self.steps(self.season)["Add venues and their grounds"].done)

    def test_draw_built_and_scheduled(self):
        for _ in range(2):
            factories.TeamFactory.create(division=self.division)
        match = factories.MatchFactory.create(stage=self.stage, date=date(2026, 7, 8))
        steps = self.steps(self.season)
        self.assertTrue(steps["Enter the teams"].done)
        self.assertTrue(steps["Build the draw"].done)
        schedule = steps["Give every match a time and a ground"]
        self.assertFalse(schedule.done)
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
            '<use href="/static/touchtechnology/admin/img/icons.svg#check"></use>'
            "</svg><span>Set-up</span>"
            '<span class="count" aria-hidden="true">3/8</span></a>'
        )
        self.assertResponseContains(
            '<p class="setup-label"><a href="%s#timeslots-tab">'
            "Add the kick-off times</a></p>" % self.season.urls["edit"]
        )

    def test_pool_edit_shows_season_progress(self):
        edit = self.pool.url_names["edit"]
        with self.login(self.superuser):
            self.assertGoodView(edit.url_name, *edit.args)
        self.assertResponseContains(
            '<a href="%s#setup-tab"><strong>Season set-up</strong> '
            "3 of 8 done</a>" % self.season.urls["edit"]
        )
        self.assertFalse(self.context["setup"].here)

    def test_competition_setup_asks_for_a_season(self):
        competition = factories.CompetitionFactory.create()
        setup = competition_setup(competition)
        self.assertEqual(
            [s.label for s in setup.steps if not s.done and not s.optional],
            ["Take in the clubs", "Add a season"],
        )
