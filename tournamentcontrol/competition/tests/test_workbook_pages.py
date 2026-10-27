"""
Tournament Control's Workbook pages: the season's and the division's set-up
checklists, the division's ladder, the hub, and where saving a day's work
returns to.
"""

import datetime

from django.contrib.auth.views import redirect_to_login
from django.urls import reverse
from freezegun import freeze_time
from test_plus import TestCase

from touchtechnology.admin.sites import site
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.admin import (
    CompetitionAdminComponent,
    division_setup,
    season_checklist,
)
from tournamentcontrol.competition.tests import factories

ICON = (
    '<svg class="wb-icon" aria-hidden="true" focusable="false">'
    '<use href="/static/touchtechnology/admin/workbook/icons.svg#%s"></use></svg>'
)


def step_html(number, title, url, note, state=""):
    """One step of a checklist as the page draws it."""
    mark = ICON % "check" if state == "is-done" else str(number)
    said = "Done:" if state == "is-done" else "To do:"
    return (
        f'<li class="wb-step {state}"><span class="wb-step-mark" aria-hidden="true">'
        f'{mark}</span><span class="wb-step-body"><span class="wb-step-title">'
        f'<a href="{url}">{title}</a></span><span class="wb-step-note">'
        f'<span class="wb-sr">{said} </span>{note}</span></span></li>'
    )


@per_shell(shells=("workbook",))
class SeasonChecklistTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.season = factories.SeasonFactory.create(
            start_date=datetime.date(2026, 9, 16)
        )
        self.division = factories.DivisionFactory.create(
            season=self.season, title="Mixed Open"
        )

    def test_the_next_step_is_the_first_one_not_done(self):
        checklist = season_checklist(self.season)
        self.assertEqual(
            [(step.key, step.done) for step in checklist.steps],
            [
                ("details", True),
                ("timeslots", False),
                ("venues", False),
                ("exclusions", False),
                ("divisions", True),
                ("teams", False),
                ("draw", False),
                ("schedule", False),
            ],
        )
        self.assertEqual(checklist.next_step.key, "timeslots")
        # The dates set aside are optional: they do not count.
        self.assertEqual((checklist.done, checklist.total), (2, 7))
        self.assertEqual(checklist.folded, False)

    def set_up_season(self):
        """
        Everything the checklist asks for, except the optional dates set
        aside, and a match played last week with no result yet.
        """
        factories.SeasonMatchTimeFactory.create(season=self.season)
        ground = factories.GroundFactory.create(venue__season=self.season)
        home, away = factories.TeamFactory.create_batch(2, division=self.division)
        played = datetime.datetime(2026, 9, 16, 18, 0, tzinfo=datetime.UTC)
        return factories.MatchFactory.create(
            stage=factories.StageFactory.create(division=self.division),
            home_team=home,
            away_team=away,
            play_at=ground,
            datetime=played,
            date=played.date(),
            time=played.time(),
        )

    @freeze_time("2026-10-01")
    def test_a_season_with_only_results_to_enter_is_all_done(self):
        self.set_up_season()
        checklist = season_checklist(self.season)
        self.assertEqual(
            [(step.key, step.done) for step in checklist.steps],
            [
                ("details", True),
                ("timeslots", True),
                ("venues", True),
                ("exclusions", False),
                ("divisions", True),
                ("teams", True),
                ("draw", True),
                ("schedule", True),
            ],
        )
        self.assertEqual((checklist.done, checklist.total), (7, 7))
        self.assertEqual(checklist.complete, True)
        self.assertEqual(checklist.next_step, None)
        self.assertEqual(checklist.folded, True)

    @freeze_time("2026-10-01")
    def test_the_season_page_folds_a_finished_checklist(self):
        self.set_up_season()
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:competition:season:edit",
                self.season.competition_id,
                self.season.pk,
            )
        self.assertEqual(self.last_response.context["setup"].folded, True)
        self.assertResponseContains(
            '<span class="wb-checklist-score">'
            f'{ICON % "circle-check"} All done</span>',
        )
        self.assertResponseContains(
            '<button type="button" class="wb-button wb-checklist-show" '
            f'data-wb-checklist-show>{ICON % "clipboard-list"}'
            "Show set-up checklist</button>",
        )
        # Results are not a set-up step, but the page still offers them.
        url = self.reverse(
            "admin:fixja:match-results",
            self.season.competition_id,
            self.season.pk,
            "20260916",
        )
        self.assertResponseContains(
            f'<a class="wb-button wb-button-primary" href="{url}">'
            f'{ICON % "list-checks"}Enter results</a>',
        )

    def test_a_division_without_teams_is_named_and_linked(self):
        step = season_checklist(self.season).steps[5]
        self.assertEqual(step.detail, "Mixed Open needs teams")
        self.assertEqual(step.url, f"{self.division.urls['edit']}#teams-tab")

    def test_the_season_page_shows_the_checklist(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:competition:season:edit",
                self.season.competition_id,
                self.season.pk,
            )
        edit = self.season.urls["edit"]
        self.assertResponseContains(
            step_html(
                1,
                "Name the season and when it starts",
                f"{edit}#season-tab",
                "Starts 16 September 2026",
                "is-done",
            ),
        )
        self.assertResponseContains(
            step_html(
                6,
                "Enter the teams",
                f"{self.division.urls['edit']}#teams-tab",
                "Mixed Open needs teams",
            ),
        )
        self.assertResponseContains(
            '<span class="wb-checklist-next">Next: Add the kick-off times</span>',
        )


@per_shell(shells=("workbook",))
class DivisionPageTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.division = factories.DivisionFactory.create(title="Men's Open")
        self.stage = factories.StageFactory.create(
            division=self.division, title="Regular Season"
        )
        self.args = (
            self.division.season.competition_id,
            self.division.season_id,
            self.division.pk,
        )

    def test_the_division_page_can_bring_a_hidden_checklist_back(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:competition:season:division:edit", *self.args
            )
        # No teams yet, so the checklist starts open.
        self.assertEqual(self.last_response.context["division_setup"].folded, False)
        self.assertResponseContains(
            '<button type="button" class="wb-button wb-checklist-show" '
            f'data-wb-checklist-show>{ICON % "clipboard-list"}'
            "Show set-up checklist</button>",
        )

    def test_a_division_needs_its_points_before_results(self):
        self.division.points_formula = None
        steps = division_setup(self.division).steps
        self.assertEqual(
            (steps[0].key, steps[0].done, steps[0].detail),
            ("points", False, "Needed before results can be saved"),
        )

    def test_the_ladder_tab_lists_each_team_in_order(self):
        first = factories.TeamFactory.create(division=self.division, title="Gulls")
        second = factories.TeamFactory.create(division=self.division, title="Herons")
        factories.LadderSummaryFactory.create(
            stage=self.stage, team=second, played=2, win=1, loss=1, points=4
        )
        factories.LadderSummaryFactory.create(
            stage=self.stage, team=first, played=2, win=2, points=6
        )
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:competition:season:division:edit", *self.args
            )
        self.assertResponseContains(
            '<a class="wb-tab" role="tab" id="ladder-tab" href="#ladder-pane" '
            'aria-controls="ladder-pane" aria-selected="false">Ladder</a>',
        )
        ladder = self.get_context("ladders")
        self.assertEqual(
            [
                (stage, [[row.team for row in rows] for pool, rows in pools])
                for stage, pools in ladder
            ],
            [(self.stage, [[first, second]])],
        )

    def test_undoing_a_draw_returns_to_the_stages(self):
        factories.MatchFactory.create(stage=self.stage)
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:division:stage:undo",
                *self.args,
                self.stage.pk,
            )
        self.assert_http_302_found(url=f"{self.division.urls['edit']}#stages-tab")


@per_shell(shells=("workbook",))
class HubTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def test_tournament_control_shows_the_seasons_in_progress(self):
        season = factories.SeasonFactory.create(title="Spring 2099")
        with self.login(self.superuser):
            self.get_check_200("admin:fixja:index")
        self.assertResponseContains(
            f'<h3><a href="{season.urls["edit"]}">Spring 2099</a></h3>'
        )


@per_shell(shells=("workbook",))
class ReturnTests(TestCase):
    """Saving a day's results or allocation returns to the season's match days."""

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.match = factories.MatchFactory.create(date=datetime.date(2026, 10, 14))
        self.season = self.match.stage.division.season

    def test_results_return_to_the_schedule_tab(self):
        data = {
            "matches-TOTAL_FORMS": "0",
            "matches-INITIAL_FORMS": "0",
            "byes-TOTAL_FORMS": "0",
            "byes-INITIAL_FORMS": "0",
        }
        with self.login(self.superuser):
            self.post(
                "admin:fixja:match-results",
                self.season.competition_id,
                self.season.pk,
                "20261014",
                data=data,
            )
        self.assert_http_302_found(url=f"{self.season.urls['edit']}#schedule-tab")


@per_shell(shells=("workbook",))
class ClubOfficialsTests(TestCase):
    """A club's page lists its officials and adds another from the tab."""

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.club = factories.ClubFactory.create()
        self.person = factories.PersonFactory.create(club=self.club)

    def test_the_club_page_offers_to_add_an_official(self):
        with self.login(self.superuser):
            self.get_check_200("admin:fixja:club:edit", self.club.pk)
        self.assertResponseContains(
            '<a class="wb-button wb-button-primary wb-button-small" href="'
            f'{self.reverse("admin:fixja:club:clubassociation:add", self.club.pk)}">'
            f"{ICON % 'plus'}Add Official</a>",
        )

    def test_adding_an_official_belongs_to_the_club(self):
        role = factories.ClubRoleFactory.create(name="Secretary")
        with self.login(self.superuser):
            self.post(
                "admin:fixja:club:clubassociation:add",
                self.club.pk,
                data={"person": str(self.person.pk), "roles": [str(role.pk)]},
            )
        self.assert_http_302_found(url=f"{self.club.urls['edit']}#staff-tab")
        self.assertEqual(
            list(self.club.staff.values_list("person", flat=True)), [self.person.pk]
        )


@per_shell(shells=("workbook",))
class TreeTests(TestCase):
    """
    The tree in the rail: the page's own component opened down to where the
    page is, and the folders the browser asks for as they are opened.
    """

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.pool = factories.StageGroupFactory.create(title="Pool Kestrel")
        self.stage = self.pool.stage
        self.division = self.stage.division
        self.season = self.division.season

    def node(self, obj, icon, current=""):
        return (
            f'<a class="wb-node-link" href="{obj.urls["edit"]}" title="{obj.title}"'
            f"{current}>{ICON % icon}"
            f'<span class="wb-node-label">{obj.title}</span></a>'
        )

    def test_a_pool_page_opens_the_tree_down_to_the_pool(self):
        with self.login(self.superuser):
            edit = self.pool.url_names["edit"]
            self.get_check_200(edit.url_name, *edit.args)
        self.assertResponseContains(self.node(self.season.competition, "trophy"))
        self.assertResponseContains(self.node(self.season, "calendar"))
        self.assertResponseContains(self.node(self.division, "layers"))
        self.assertResponseContains(self.node(self.stage, "git-merge"))
        self.assertResponseContains(
            self.node(self.pool, "users-round", ' aria-current="page"')
        )

    def test_the_trail_to_a_team_passes_its_folder(self):
        team = factories.TeamFactory.create(division=self.division)
        explorer = site._components[CompetitionAdminComponent].explorer()
        self.assertEqual(
            explorer.trail_of(team),
            [
                "fixja/s0",
                f"fixja/o:competition.competition:{self.season.competition.pk}",
                f"fixja/o:competition.season:{self.season.pk}",
                f"fixja/o:competition.division:{self.division.pk}",
                f"fixja/g:competition.division:{self.division.pk}:teams",
                f"fixja/o:competition.team:{team.pk}",
            ],
        )

    def test_opening_a_season_lists_its_divisions(self):
        key = f"fixja/o:competition.season:{self.season.pk}"
        with self.login(self.superuser):
            self.get_check_200("admin:explorer", data={"node": key})
        self.assertResponseContains(self.node(self.division, "layers"))

    def test_the_phone_drills_into_a_division(self):
        key = f"fixja/o:competition.division:{self.division.pk}"
        with self.login(self.superuser):
            self.get_check_200("admin:explorer", data={"node": key, "mode": "drill"})
        self.assertResponseContains(
            f'<a class="wb-drill-title" href="{self.division.urls["edit"]}">'
            f"{self.division.title}</a>",
        )

    def test_an_unknown_component_is_not_found(self):
        with self.login(self.superuser):
            self.get("admin:explorer", data={"node": "nowhere/"})
        self.assert_http_404_not_found()

    def test_only_staff_may_open_folders(self):
        self.get("admin:explorer", data={"node": "fixja/"})
        folder = reverse("admin:explorer", query={"node": "fixja/"})
        self.assert_http_302_found(url=redirect_to_login(folder, "admin:login").url)
