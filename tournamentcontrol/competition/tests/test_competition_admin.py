import base64
import copy
import unittest
from datetime import date, datetime, time
from itertools import count
from unittest.mock import ANY, MagicMock, PropertyMock, patch
from zoneinfo import ZoneInfo

import cloudinary
import responses
from dateutil.rrule import DAILY
from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages.test import MessagesTestMixin
from django.db import connection
from django.template import Context, Template
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from guardian.shortcuts import assign_perm
from test_plus import TestCase as BaseTestCase

from touchtechnology.admin.branding import get_brand
from touchtechnology.admin.sites import site
from touchtechnology.admin.tests.shells import ArrowMixin, IconMixin, by_shell, per_shell
from touchtechnology.common.tests.factories import (
    StaffFactory,
    SuperUserFactory,
    UserFactory,
)
from tournamentcontrol.competition.dashboard import MostValuableWidget
from tournamentcontrol.competition.draw.schemas import (
    DivisionStructure,
    StageFixture,
)
from tournamentcontrol.competition.models import (
    Division,
    Ground,
    Match,
    MatchScoreSheet,
    SeasonAssociation,
    SimpleScoreMatchStatistic,
    Stage,
    StageGroup,
    Team,
    TeamAssociation,
    UndecidedTeam,
)
from tournamentcontrol.competition.tasks import generate_pdf_scorecards
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.utils import round_robin, round_robin_format

#: The home page's budget: the widgets' queries, and two for its jobs (the
#: latest day with results to enter and the next match day). It holds however
#: many stages, seasons or matches there are.
DASHBOARD_QUERIES = 16

#: An icon of the admin's sprite, as the pages draw it.
ICON = (
    '<svg class="wb-icon" aria-hidden="true" focusable="false">'
    '<use href="/static/touchtechnology/admin/workbook/icons.svg#%s"></use></svg>'
)


def bulk_link(url, name, title):
    """Explorer's "Add several" control: a link, the dialog is the page's own."""
    return (
        f'<a class="button compact" href="{url}?count=5" '
        f'data-add-many="add-many-{name}">'
        '<svg class="icon" aria-hidden="true" focusable="false"><use '
        'href="/static/touchtechnology/admin/explorer/img/icons.svg#plus-many">'
        f"</use></svg><span>{title}</span></a>"
    )


def bulk_dialog(url, name, title):
    """The "Add several" control a tab offers: a button and the dialog it opens."""
    return (
        f'<form method="get" action="{url}" class="wb-inline-form">'
        f'<button type="submit" class="wb-button wb-button-small" '
        f'data-wb-dialog="bulk-{name}" aria-label="{title}">'
        f'{ICON % "copy-plus"}Add several</button>'
        f'<dialog class="wb-dialog" id="bulk-{name}" '
        f'aria-labelledby="bulk-{name}-title"><div class="wb-dialog-body">'
        f'<h2 class="wb-dialog-title" id="bulk-{name}-title">{title}</h2>'
        '<div class="wb-field">'
        f'<label class="wb-label" for="bulk-{name}-count">'
        "How many do you want to add?</label>"
        f'<input class="wb-input" type="number" id="bulk-{name}-count" '
        'name="count" min="1" max="50" value="5" required>'
        '<p class="wb-help">You get a row for each, to fill in on one page. '
        "Rows left blank are ignored.</p></div>"
        '<div class="wb-dialog-actions">'
        '<button type="button" class="wb-button wb-button-quiet" '
        "data-wb-dialog-close>Cancel</button>"
        '<button type="submit" class="wb-button wb-button-primary">Continue</button>'
        "</div></div></dialog></form>"
    )


class TestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def assertGoodEditView(self, viewname, *args, **kwargs):
        test_query_count = kwargs.pop("test_query_count", 50)
        self.assertLoginRequired(viewname, *args)
        with self.login(self.superuser):
            self.assertGoodView(viewname, test_query_count=test_query_count, *args)
            if kwargs:
                self.post(viewname, *args, **kwargs)
                self.response_302()

    def assertGoodDeleteView(self, viewname, *args):
        self.assertLoginRequired(viewname, *args)
        with self.login(self.superuser):
            self.get(viewname, *args)
            self.response_405()
            self.post(viewname, *args)
            self.response_302()

    def assertGoodNamespace(self, instance, **kwargs):
        namespace = instance._get_admin_namespace()
        args = instance._get_url_args()
        self.assertGoodEditView(f"{namespace}:add", *args[:-1], **kwargs)
        self.assertGoodEditView(f"{namespace}:edit", *args, **kwargs)
        self.assertGoodDeleteView(f"{namespace}:delete", *args)


class TemplateTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        stage1 = factories.StageFactory.create()
        stage2 = factories.StageFactory.create(division=stage1.division, follows=stage1)
        ground = factories.GroundFactory.create(venue__season=stage2.division.season)
        cls.team = factories.TeamFactory.create(
            title="Chees\u00e9\u00a0&\u00a0Crackers", division=stage1.division
        )
        factories.MatchFactory.create(
            home_team=None,
            away_team=None,
            home_team_eval="P1",
            away_team_eval="P2",
            stage=stage2,
            date=date(2017, 2, 13),
            time=time(9, 0),
            play_at=ground,
            datetime=datetime(2017, 2, 13, 9, tzinfo=ZoneInfo("UTC")),
        )
        factories.MatchFactory.create(
            home_team=cls.team,
            away_team=None,
            home_team_eval="P3",
            away_team_eval="P4",
            stage=stage2,
            date=date(2017, 2, 13),
            time=time(10, 0),
            play_at=ground,
            datetime=datetime(2017, 2, 13, 10, tzinfo=ZoneInfo("UTC")),
        )
        cls.stage = stage2
        cls.division = stage2.division
        cls.season = cls.division.season
        cls.competition = cls.season.competition

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()

    def test_team_title(self):
        template = Template("{% load common %}{{ team.title|htmlentities }}")
        context = Context({"team": self.team})
        output = template.render(context)
        self.assertEqual(output, "Chees&eacute;&nbsp;&amp;&nbsp;Crackers")

    def test_match_runsheet(self):
        self.assertLoginRequired(
            "admin:fixja:match-runsheet",
            self.competition.pk,
            self.season.pk,
            "20170213",
        )
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:match-runsheet",
                self.competition.pk,
                self.season.pk,
                "20170213",
            )
            cell = by_shell(workbook="<td>%s</td>", explorer='<td class="team">%s</td>')
            self.assertResponseContains(cell % "1st")
            self.assertResponseContains(cell % "2nd ")  # whitespace deliberate
            self.assertResponseContains(cell % "Chees&eacute;&nbsp;&amp;&nbsp;Crackers")

    def test_match_grid(self):
        self.assertLoginRequired(
            "admin:fixja:match-grid",
            self.competition.pk,
            self.season.pk,
            "20170213",
            "html",
        )
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:match-grid",
                self.competition.pk,
                self.season.pk,
                "20170213",
                "html",
            )
            for fragment in by_shell(
                workbook=(f"<h4>{self.division} <small>{self.stage}</small></h4>",),
                explorer=(
                    f"<strong>{self.division}</strong>",
                    f"<small>{self.stage}</small>",
                ),
            ):
                self.assertResponseContains(fragment)
            box = by_shell(workbook="<p>%s</p>", explorer="<div>%s</div>")
            self.assertResponseContains(
                box % "1st <br>2nd"
            )  # whitespace & br style deliberate
            self.assertResponseContains(
                box % "Chees&eacute;&nbsp;&amp;&nbsp;Crackers<br>4th"
            )

    def test_scorecards_html(self):
        # Regression test for #82: the scorecards template does
        # ``{% load common %}`` and must render.
        self.assertLoginRequired(
            "admin:fixja:scorecards",
            self.competition.pk,
            self.season.pk,
            "20170213",
            "html",
        )
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:scorecards",
                self.competition.pk,
                self.season.pk,
                "20170213",
                "html",
            )
            self.assertResponseContains(
                by_shell(
                    workbook=f"<title>Scorecards &middot; {get_brand().name}</title>",
                    explorer="<title>Scorecards</title>",
                )
            )
            css = by_shell(workbook="p-card-team team", explorer="team")
            self.assertResponseContains(
                f'<th colspan="5" class="{css}">'
                "Chees&eacute;&nbsp;&amp;&nbsp;Crackers</th>"
            )

    @patch("tournamentcontrol.competition.utils.prince")
    def test_scorecards_pdf_task(self, mock_prince):
        # Regression test for #82: the PDF variant renders the same template
        # inside the celery task (a fresh worker process in production)
        # before handing the markup to Prince. Called the way the admin view
        # queues it since #42: primary keys only, the task loads the season
        # and competition for the template itself.
        mock_prince.return_value = b"%PDF-1.4"
        templates = site.shell.names(
            "tournamentcontrol/competition/admin/scorecards.html"
        )
        match_pks = list(self.season.matches.values_list("pk", flat=True))
        data = generate_pdf_scorecards(
            match_pks, templates, {}, season_pk=self.season.pk
        )
        self.assertEqual(base64.b64decode(data), b"%PDF-1.4")
        mock_prince.assert_called_once()
        html = mock_prince.call_args.args[0]
        self.assertIn(
            by_shell(
                workbook=f"<title>Scorecards \u00b7 {get_brand().name}</title>",
                explorer="<title>Scorecards</title>",
            ),
            html,
        )
        css = by_shell(workbook="p-card-team team", explorer="team")
        self.assertIn(
            f'<th colspan="5" class="{css}">Chees\u00e9\u00a0&amp;\u00a0Crackers</th>',
            html,
        )


@per_shell
class ReorderTests(MessagesTestMixin, ArrowMixin, BaseTestCase):
    """
    The arrows of a division's stages and of its teams: each is a form that
    posts, moves the row past its neighbour and returns to the tab it is in.
    Following the address moves nothing. A row has arrows, and may be moved,
    only by a person who may change it; a move off either end of the list
    changes nothing.
    """

    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        cls.superuser = cls.make_user("superuser")
        cls.division = factories.DivisionFactory.create()
        cls.stages = [
            factories.StageFactory.create(division=cls.division, title=title, order=n)
            for n, title in enumerate(("Pool play", "Semi-finals", "Finals"), 1)
        ]
        cls.teams = [
            factories.TeamFactory.create(division=cls.division, title=title, order=n)
            for n, title in enumerate(("Ants", "Bees", "Cats"), 1)
        ]
        # Two members of staff who may open the division and add to its
        # lists, so every row is drawn for them: the editor may also change
        # the second stage and the second team, the viewer nothing.
        cls.viewer = StaffFactory.create(username="viewer")
        cls.editor = StaffFactory.create(username="editor")
        for user in (cls.viewer, cls.editor):
            assign_perm("competition.change_division", user, cls.division)
            assign_perm("competition.add_stage", user)
            assign_perm("competition.add_team", user)
        assign_perm("competition.change_stage", cls.editor, cls.stages[1])
        assign_perm("competition.change_team", cls.editor, cls.teams[1])

    def get_division(self):
        self.get_check_200(
            "admin:fixja:competition:season:division:edit",
            self.division.season.competition_id,
            self.division.season_id,
            self.division.pk,
        )

    def title_cell(self, obj):
        """The first cell of ``obj``'s row, for a person who may not edit it."""
        css = self.by_shell(workbook="wb-title-cell", explorer="title-cell")
        return f'<td class="{css}"><span>{obj.title}</span></td>'

    def assertArrows(self, assertion):
        """``assertion`` holds for both arrows of every stage and every team."""
        lists = (("stage:division", self.stages), ("team:division", self.teams))
        for route, rows in lists:
            for obj in rows:
                for direction in ("up", "down"):
                    with self.subTest(obj=obj.title, direction=direction):
                        action = self.reverse(
                            "admin:fixja:reorder", route, obj.pk, direction
                        )
                        assertion(self.arrow(action, direction, obj.title))

    def test_a_visitor_is_asked_to_sign_in(self):
        self.assertLoginRequired(
            "admin:fixja:reorder", "stage:division", self.stages[1].pk, "down"
        )

    def test_each_row_has_arrows_that_post(self):
        with self.login(self.superuser):
            self.get_division()
        self.assertArrows(self.assertResponseContains)

    def test_a_person_who_may_not_change_the_rows_sees_no_arrows(self):
        with self.login(self.viewer):
            self.get_division()
        for obj in (*self.stages, *self.teams):
            with self.subTest(obj=obj.title):
                self.assertResponseContains(self.title_cell(obj))
        self.assertArrows(self.assertResponseNotContains)

    def test_the_arrows_are_drawn_for_the_rows_the_person_may_change(self):
        pool_play, semi_finals, finals = self.stages
        ants, bees, cats = self.teams
        with self.login(self.editor):
            self.get_division()
        for route, obj in (("stage:division", semi_finals), ("team:division", bees)):
            for direction in ("up", "down"):
                with self.subTest(obj=obj.title, direction=direction):
                    action = self.reverse(
                        "admin:fixja:reorder", route, obj.pk, direction
                    )
                    self.assertResponseContains(
                        self.arrow(action, direction, obj.title)
                    )
        for route, obj in (
            ("stage:division", pool_play),
            ("stage:division", finals),
            ("team:division", ants),
            ("team:division", cats),
        ):
            with self.subTest(obj=obj.title):
                self.assertResponseContains(self.title_cell(obj))
            for direction in ("up", "down"):
                with self.subTest(obj=obj.title, direction=direction):
                    action = self.reverse(
                        "admin:fixja:reorder", route, obj.pk, direction
                    )
                    self.assertResponseNotContains(
                        self.arrow(action, direction, obj.title)
                    )

    def test_a_person_who_may_not_change_a_stage_may_not_move_it(self):
        semi_finals = self.stages[1]
        with self.login(self.viewer):
            self.post("admin:fixja:reorder", "stage:division", semi_finals.pk, "down")
        self.assert_http_403_forbidden()
        self.assertEqual(list(self.division.stages.all()), self.stages)

    def test_a_person_who_may_change_a_stage_moves_it(self):
        pool_play, semi_finals, finals = self.stages
        with self.login(self.editor):
            self.post("admin:fixja:reorder", "stage:division", semi_finals.pk, "down")
            self.assert_http_302_found(url=f"{self.division.urls['edit']}#stages-tab")
            self.get_check_200(self.last_response.url)
        self.assertEqual(
            list(self.division.stages.all()), [pool_play, finals, semi_finals]
        )

    def test_the_permission_to_move_a_stage_is_checked_on_that_stage(self):
        pool_play = self.stages[0]
        with self.login(self.editor):
            self.post("admin:fixja:reorder", "stage:division", pool_play.pk, "down")
        self.assert_http_403_forbidden()
        self.assertEqual(list(self.division.stages.all()), self.stages)

    def test_moving_a_stage_down_returns_to_the_stages(self):
        pool_play, semi_finals, finals = self.stages
        with self.login(self.superuser):
            self.post("admin:fixja:reorder", "stage:division", semi_finals.pk, "down")
            self.assert_http_302_found(url=f"{self.division.urls['edit']}#stages-tab")
            self.assertMessages(
                self.last_response,
                [
                    messages.Message(
                        messages.INFO,
                        'The stage "Semi-finals" has been reordered down the list.',
                    )
                ],
            )
            self.get_check_200(self.last_response.url)
        self.assertEqual(
            list(self.division.stages.all()), [pool_play, finals, semi_finals]
        )

    def test_moving_a_stage_up_returns_to_the_stages(self):
        pool_play, semi_finals, finals = self.stages
        with self.login(self.superuser):
            self.post("admin:fixja:reorder", "stage:division", semi_finals.pk, "up")
            self.assert_http_302_found(url=f"{self.division.urls['edit']}#stages-tab")
            self.get_check_200(self.last_response.url)
        self.assertEqual(
            list(self.division.stages.all()), [semi_finals, pool_play, finals]
        )

    def test_moving_a_team_down_returns_to_the_teams(self):
        ants, bees, cats = self.teams
        with self.login(self.superuser):
            self.post("admin:fixja:reorder", "team:division", ants.pk, "down")
            self.assert_http_302_found(url=f"{self.division.urls['edit']}#teams-tab")
            self.get_check_200(self.last_response.url)
        self.assertEqual(list(self.division.teams.all()), [bees, ants, cats])

    def test_an_address_without_a_parent_returns_to_the_object(self):
        stage = self.stages[0]
        pools = [
            factories.StageGroupFactory.create(stage=stage, order=n) for n in (1, 2)
        ]
        with self.login(self.superuser):
            self.post("admin:fixja:reorder", "stagegroup", pools[0].pk, "down")
            self.assert_http_302_found(url=pools[0].urls["edit"])
            self.get_check_200(self.last_response.url)
        self.assertEqual(list(stage.pools.all()), pools[::-1])

    def test_following_the_address_moves_nothing(self):
        with self.login(self.superuser):
            self.get("admin:fixja:reorder", "stage:division", self.stages[1].pk, "down")
        self.assert_http_405_method_not_allowed()
        self.assertEqual(list(self.division.stages.all()), self.stages)

    def test_moving_the_first_stage_up_returns_to_the_stages_unchanged(self):
        first = self.stages[0]
        with self.login(self.superuser):
            self.post("admin:fixja:reorder", "stage:division", first.pk, "up")
            self.assert_http_302_found(url=f"{self.division.urls['edit']}#stages-tab")
            self.assertMessages(self.last_response, [])
        self.assertEqual(list(self.division.stages.all()), self.stages)

    def test_moving_the_last_stage_down_returns_to_the_stages_unchanged(self):
        last = self.stages[-1]
        with self.login(self.superuser):
            self.post("admin:fixja:reorder", "stage:division", last.pk, "down")
            self.assert_http_302_found(url=f"{self.division.urls['edit']}#stages-tab")
            self.assertMessages(self.last_response, [])
        self.assertEqual(list(self.division.stages.all()), self.stages)

    def test_a_model_that_is_not_in_an_order_is_not_found(self):
        semi_finals = self.stages[1]
        for model in ("ladder", "match"):
            with self.subTest(model=model), self.login(self.superuser):
                self.post(
                    "admin:fixja:reorder", f"{model}:division", semi_finals.pk, "down"
                )
                self.assert_http_404_not_found()
        self.assertEqual(list(self.division.stages.all()), self.stages)

    def test_a_stage_that_does_not_exist_is_not_found(self):
        gone = self.stages[-1].pk + 1
        with self.login(self.superuser):
            self.post("admin:fixja:reorder", "stage:division", gone, "down")
        self.assert_http_404_not_found()
        self.assertEqual(list(self.division.stages.all()), self.stages)

    def test_a_parent_the_model_does_not_have_is_not_found(self):
        with self.login(self.superuser):
            self.post("admin:fixja:reorder", "stage:league", self.stages[1].pk, "down")
        self.assert_http_404_not_found()
        self.assertEqual(list(self.division.stages.all()), self.stages)

    def test_a_stage_moves_only_up_or_down(self):
        middle = self.stages[1]
        with self.login(self.superuser):
            self.post("admin:fixja:reorder", "stage:division", middle.pk, "left")
        self.assert_http_404_not_found()
        self.assertEqual(list(self.division.stages.all()), self.stages)


class GoodViewTests(TestCase):
    def test_index(self):
        """
        Where the shell has landing pages Tournament Control opens on its own
        page, its jobs and sections; where it has none it goes straight to the
        list of competitions.
        """
        self.assertLoginRequired("admin:fixja:index")
        with self.login(self.superuser):
            self.get("admin:fixja:index")
            if site.shell.index_landing:
                self.response_200()
                url = self.reverse("admin:fixja:competition:list")
                self.assertResponseContains(
                    f'<a class="wb-task" href="{url}">'
                    f'<span class="wb-task-icon">{ICON % "chevron-right"}</span>'
                    '<span class="wb-task-title">Competitions</span></a>',
                )
            else:
                self.response_302()

    def test_competition(self):
        competition = factories.CompetitionFactory.create()
        self.assertLoginRequired("admin:fixja:competition:list")
        with self.login(self.superuser):
            self.assertGoodView("admin:fixja:competition:list")
        self.assertGoodNamespace(competition)

    def test_clubrole(self):
        role = factories.ClubRoleFactory.create()
        self.assertGoodNamespace(role, data={"name": "Club Role"})

    def test_teamrole(self):
        role = factories.TeamRoleFactory.create()
        self.assertGoodNamespace(role, data={"name": "Team Role"})

    def test_season(self):
        season = factories.SeasonFactory.create()
        self.assertGoodNamespace(season)

    def test_season_exclusion(self):
        exclusion = factories.SeasonExclusionDateFactory.create()
        self.assertGoodNamespace(exclusion)

    def test_timeslot(self):
        matchtime = factories.SeasonMatchTimeFactory.create()
        self.assertGoodNamespace(matchtime)

    def test_livestreamevent(self):
        event = factories.LiveStreamEventFactory.create(season__live_stream=True)
        self.assertGoodNamespace(event)

    def test_livestreamkey(self):
        stream_key = factories.LiveStreamKeyFactory.create(season__live_stream=True)
        self.assertGoodNamespace(stream_key)

    def test_venue(self):
        venue = factories.VenueFactory.create()
        self.assertGoodNamespace(venue)

    def test_ground(self):
        ground = factories.GroundFactory.create()
        self.assertGoodNamespace(ground)

    def test_division(self):
        division = factories.DivisionFactory.create()
        self.assertGoodNamespace(division)

    def test_division_exclusion(self):
        exclusion = factories.DivisionExclusionDateFactory.create()
        self.assertGoodNamespace(exclusion)

    def test_team(self):
        team = factories.TeamFactory.create()
        self.assertGoodNamespace(team)

    def test_teamassociation(self):
        team_association = factories.TeamAssociationFactory.create()
        self.assertGoodNamespace(team_association)

    def test_stage(self):
        stage = factories.StageFactory.create()
        self.assertGoodNamespace(stage, test_query_count=100)

    def test_match(self):
        match = factories.MatchFactory.create()
        self.assertGoodNamespace(match)

    @patch.multiple(
        cloudinary.config(),
        create=True,
        cloud_name="test",
        api_key="test",
        api_secret="test",
    )
    def test_match_scoresheet(self):
        scoresheet = MatchScoreSheet.objects.create(
            match=factories.MatchFactory.create(), image="harness/score-sheet"
        )
        self.assertGoodNamespace(scoresheet)

    @patch.multiple(
        cloudinary.config(),
        create=True,
        cloud_name="test",
        api_key="test",
        api_secret="test",
    )
    def test_match_with_scoresheet(self):
        match = factories.MatchFactory.create()
        MatchScoreSheet.objects.create(match=match, image="harness/score-sheet")
        with self.login(self.superuser):
            self.get(f"{match._get_admin_namespace()}:edit", *match._get_url_args())
            self.response_200()

    def test_pool(self):
        pool = factories.StageGroupFactory.create()
        self.assertGoodNamespace(pool)

    @unittest.skip(
        "django-guardian bug - see "
        "https://github.com/django-guardian/django-guardian/issues/519"
    )
    def test_club(self):
        club = factories.ClubFactory.create()
        self.assertLoginRequired("admin:fixja:club:list")
        with self.login(self.superuser):
            self.assertGoodView("admin:fixja:club:list")
        self.assertGoodNamespace(club)

    def test_person(self):
        person = factories.PersonFactory.create()
        self.assertFalse(person.statistics.count())
        self.assertGoodNamespace(person)

    def test_format(self):
        draw_format = factories.DrawFormatFactory.create()
        self.assertLoginRequired("admin:fixja:format:list")
        with self.login(self.superuser):
            self.assertGoodView("admin:fixja:format:list")
        self.assertGoodNamespace(draw_format)

    @unittest.skip("Not refactored as a namespace yet")
    def test_list_drawformat(self):
        self.assertLoginRequired("admin:fixja:report:list")
        with self.login(self.superuser):
            self.assertGoodView("admin:fixja:report:list")

    # code coverage

    def test_season_report(self):
        season = factories.SeasonFactory.create()
        self.assertLoginRequired(
            "admin:fixja:competition:season:report", season.competition_id, season.pk
        )
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:competition:season:report",
                season.competition_id,
                season.pk,
            )

    def test_season_summary(self):
        season = factories.SeasonFactory.create()
        self.assertLoginRequired(
            "admin:fixja:competition:season:summary", season.competition_id, season.pk
        )
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:competition:season:summary",
                season.competition_id,
                season.pk,
            )

    def test_match_schedule_season(self):
        season = factories.SeasonFactory.create()
        ground = factories.GroundFactory.create(venue__season=season)
        match = factories.MatchFactory.create(
            date=date(2017, 2, 13),
            stage__division__season=season,
        )
        args = (season.competition_id, season.pk, match.date.strftime("%Y%m%d"))
        self.assertLoginRequired("admin:fixja:match-schedule", *args)
        with self.login(self.superuser):
            self.assertGoodView("admin:fixja:match-schedule", *args)
            self.assertResponseContains(
                '<input type="hidden" name="form-TOTAL_FORMS" value="1" id="id_form-TOTAL_FORMS">'
            )
            self.post(
                "admin:fixja:match-schedule",
                *args,
                data={
                    "form-ignore_clashes": "0",
                    "form-TOTAL_FORMS": "1",
                    "form-INITIAL_FORMS": "1",
                    "form-MIN_NUM_FORMS": "",
                    "form-MAX_NUM_FORMS": "1000",
                    "form-0-id": match.pk,
                    "form-0-time": "10:00",
                    "form-0-play_at": ground.pk,
                },
            )
            self.response_302()

    def test_match_live_stream_requires_staff_login(self):
        stage = factories.StageFactory.create()
        camera_ground = factories.GroundFactory.create(
            venue__season=stage.division.season, live_stream=True
        )
        factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            date=date(2025, 5, 1),
            time=time(14, 0),
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
        )
        season = stage.division.season

        self.assertLoginRequired(
            "admin:fixja:match-live-stream",
            season.competition.pk,
            season.pk,
            "20250501",
        )

    def test_match_live_stream_resync_requires_staff_login(self):
        stage = factories.StageFactory.create()
        camera_ground = factories.GroundFactory.create(
            venue__season=stage.division.season, live_stream=True
        )
        factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            live_stream=True,
            external_identifier="yt-broadcast-1",
            date=date(2025, 5, 1),
            time=time(14, 0),
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
        )
        season = stage.division.season

        self.assertLoginRequired(
            "admin:fixja:match-live-stream-resync",
            season.competition.pk,
            season.pk,
            "20250501",
        )

    def test_match_schedule_division(self):
        division = factories.DivisionFactory.create()
        self.assertLoginRequired(
            "admin:fixja:match-schedule",
            competition_id=division.season.competition_id,
            season_id=division.season_id,
            datestr="20170213",
            division_id=division.pk,
        )
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:match-schedule",
                competition_id=division.season.competition_id,
                season_id=division.season_id,
                datestr="20170213",
                division_id=division.pk,
            )

    def test_progress_teams(self):
        division = factories.DivisionFactory.create()
        teams = factories.TeamFactory.create_batch(division=division, size=6)

        round_games, finals = factories.StageFactory.create_batch(
            division=division, size=2
        )

        url_rounds = round_games.url_names["progress"]
        url_finals = finals.url_names["progress"]

        for round in round_robin(teams):
            for home_team, away_team in round:
                factories.MatchFactory.create(
                    stage=round_games,
                    home_team=home_team,
                    away_team=away_team,
                )

        # Easier to just build the 3 matches required for progression than to
        # automate it more extensively.
        semi_1 = factories.MatchFactory.create(
            stage=finals,
            label="Semi 1",
            round=6,
            home_team=None,
            home_team_eval="P1",
            away_team=None,
            away_team_eval="P4",
        )
        semi_2 = factories.MatchFactory.create(
            stage=finals,
            label="Semi 2",
            round=6,
            home_team=None,
            home_team_eval="P2",
            away_team=None,
            away_team_eval="P3",
        )
        factories.MatchFactory.create(
            stage=finals,
            label="Final",
            round=7,
            home_team=None,
            home_team_eval="W",
            home_team_eval_related=semi_1,
            away_team=None,
            away_team_eval="W",
            away_team_eval_related=semi_2,
        )

        self.assertLoginRequired(url_rounds.url_name, *url_rounds.args)

        with self.login(self.superuser):
            # The round games cannot be progressed, it's the first stage and
            # therefore can't have any undecided teams.
            self.get(url_rounds.url_name, *url_rounds.args)
            self.response_410()

            # FIXME
            #
            # # The final series can't be progressed because there are results
            # # that need to be entered for matches in the preceding stage.
            # self.get(finals._get_admin_namespace() + ':progress',
            #          *finals._get_url_args())
            # self.response_410()
            #
            # # Set random results for every unplayed match in the previous stage
            # # so that we can determine progressions.
            # for m in round_games.matches.all():
            #     m.home_team_score = random.randint(0, 20)
            #     m.away_team_score = random.randint(0, 20)

            # The final series progression should now be accessible.
            self.get(url_finals.url_name, *url_finals.args)
            self.response_200()

    def test_progress_teams_position_before_undecided(self):
        """
        Regression test for issue #62.

        A finals series which mixes positional references (P1..P6) with
        undecided teams whose identity depends on the result of matches in the
        same stage ("Lower placed qualifier") must progress the positional
        references first. The undecided teams can only be chosen once the
        qualifying matches have been played.
        """
        division = factories.DivisionFactory.create()
        teams = factories.TeamFactory.create_batch(division=division, size=6)

        round_games = factories.StageFactory.create(division=division, order=1)
        finals = factories.StageFactory.create(
            division=division, order=2, follows=round_games
        )

        # Lower index team always wins, so the ladder is teams[0] .. teams[5]
        for round in round_robin(teams):
            for home_team, away_team in round:
                winner = min(home_team, away_team, key=teams.index)
                factories.MatchFactory.create(
                    stage=round_games,
                    home_team=home_team,
                    away_team=away_team,
                    home_team_score=5 if winner == home_team else 0,
                    away_team_score=5 if winner == away_team else 0,
                )

        lower = finals.undecided_teams.create(label="Lower placed qualifier")
        higher = finals.undecided_teams.create(label="Higher placed qualifier")

        qual_1 = factories.MatchFactory.create(
            stage=finals,
            label="Qualifier 1",
            round=1,
            home_team=None,
            home_team_eval="P3",
            away_team=None,
            away_team_eval="P6",
        )
        qual_2 = factories.MatchFactory.create(
            stage=finals,
            label="Qualifier 2",
            round=1,
            home_team=None,
            home_team_eval="P4",
            away_team=None,
            away_team_eval="P5",
        )
        semi_1 = factories.MatchFactory.create(
            stage=finals,
            label="Semi 1",
            round=2,
            home_team=None,
            home_team_eval="P1",
            away_team=None,
            away_team_undecided=lower,
        )
        semi_2 = factories.MatchFactory.create(
            stage=finals,
            label="Semi 2",
            round=2,
            home_team=None,
            home_team_eval="P2",
            away_team=None,
            away_team_undecided=higher,
        )

        url = finals.url_names["progress"]

        with self.login(self.superuser):
            # Positional references from the previous stage can be resolved
            # immediately, so the match progression form must be presented.
            self.get(url.url_name, *url.args)
            self.response_200()
            self.assertTemplateUsed(
                self.last_response,
                site.shell.shelled(
                    "tournamentcontrol/competition/admin/progress_matches.html"
                ),
            )
            formset = self.get_context("formset")
            self.assertEqual(formset.model, Match)
            # The undecided teams are not offered for selection yet, they can
            # only be identified once the qualifiers have been played.
            self.assertEqual(
                {
                    form.instance.pk: {
                        name: form.initial[name] for name in form.fields if name != "id"
                    }
                    for form in formset.forms
                },
                {
                    qual_1.pk: {"home_team": teams[2], "away_team": teams[5]},
                    qual_2.pk: {"home_team": teams[3], "away_team": teams[4]},
                    semi_1.pk: {"home_team": teams[0]},
                    semi_2.pk: {"home_team": teams[1]},
                },
            )

            data = {
                "form-TOTAL_FORMS": "4",
                "form-INITIAL_FORMS": "4",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
            }
            for i, (match, home, away) in enumerate(
                [
                    (qual_1, teams[2], teams[5]),
                    (qual_2, teams[3], teams[4]),
                    (semi_1, teams[0], None),
                    (semi_2, teams[1], None),
                ]
            ):
                data[f"form-{i}-id"] = str(match.pk)
                data[f"form-{i}-home_team"] = str(home.pk)
                if away is not None:
                    data[f"form-{i}-away_team"] = str(away.pk)

            self.post(url.url_name, *url.args, data=data)
            self.assert_http_302_found(url=str(division.season.urls["edit"]))

            for match in (qual_1, qual_2, semi_1, semi_2):
                match.refresh_from_db()

            self.assertEqual((qual_1.home_team, qual_1.away_team), (teams[2], teams[5]))
            self.assertEqual((qual_2.home_team, qual_2.away_team), (teams[3], teams[4]))
            self.assertEqual((semi_1.home_team, semi_1.away_team), (teams[0], None))
            self.assertEqual((semi_2.home_team, semi_2.away_team), (teams[1], None))

            # P6 upsets P3 and P4 beats P5; P6 is the lower placed qualifier.
            qual_1.home_team_score, qual_1.away_team_score = 2, 3
            qual_1.save()
            qual_2.home_team_score, qual_2.away_team_score = 3, 2
            qual_2.save()

            # Only the undecided teams remain to be progressed.
            self.get(url.url_name, *url.args)
            self.response_200()
            self.assertTemplateUsed(
                self.last_response,
                site.shell.shelled(
                    "tournamentcontrol/competition/admin/progress_teams.html"
                ),
            )
            formset = self.get_context("formset")
            self.assertEqual(formset.model, UndecidedTeam)
            self.assertCountEqual(
                [form.instance for form in formset.forms], [lower, higher]
            )

            data = {
                "form-TOTAL_FORMS": "2",
                "form-INITIAL_FORMS": "2",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
            }
            for i, (undecided, team) in enumerate(
                [(lower, teams[5]), (higher, teams[3])]
            ):
                data[f"form-{i}-id"] = str(undecided.pk)
                data[f"form-{i}-team"] = str(team.pk)

            self.post(url.url_name, *url.args, data=data)
            self.response_302()

            semi_1.refresh_from_db()
            semi_2.refresh_from_db()
            self.assertEqual((semi_1.home_team, semi_1.away_team), (teams[0], teams[5]))
            self.assertEqual((semi_2.home_team, semi_2.away_team), (teams[1], teams[3]))

            # Nothing left to progress.
            self.get(url.url_name, *url.args)
            self.response_410()

    def test_progression_list(self):
        rounds = factories.StageFactory.create(order=1)
        finals = factories.StageFactory.create(
            division=rounds.division, order=2, follows=rounds
        )
        factories.MatchFactory.create(
            stage=finals,
            home_team=None,
            home_team_eval="P1",
            away_team=None,
            away_team_eval="P2",
        )
        season = finals.division.season
        self.assertLoginRequired(
            "admin:fixja:competition:season:progression-list",
            season.competition_id,
            season.pk,
        )
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:competition:season:progression-list",
                season.competition_id,
                season.pk,
            )
        url = self.reverse(
            "admin:fixja:competition:season:division:stage:progress",
            season.competition_id,
            season.pk,
            finals.division_id,
            finals.pk,
        )
        self.assertResponseContains(
            by_shell(
                workbook=f'<a href="{url}">Progress teams</a>',
                explorer=f'<a href="{url}">Place the teams</a>',
            )
        )

    def test_edit_person(self):
        person = factories.PersonFactory.create()
        self.assertLoginRequired("admin:fixja:club:person:add", person.club.pk)
        self.assertLoginRequired(
            "admin:fixja:club:person:edit", person.club.pk, person.pk
        )
        with self.login(self.superuser):
            self.assertGoodView("admin:fixja:club:person:add", person.club.pk)
            self.assertGoodView(
                "admin:fixja:club:person:edit", person.club.pk, person.pk
            )

    def test_edit_club_primary_contact_choices(self):
        "A club's primary contact is chosen from its own people, not the site's."
        club = factories.ClubFactory.create()
        member = factories.PersonFactory.create(club=club)
        outsider = factories.PersonFactory.create()

        with self.login(self.superuser):
            self.get("admin:fixja:club:edit", club.pk)
            self.response_200()

        self.assertResponseContains(f'<option value="{member.pk}">{member}</option>')
        self.assertResponseNotContains(
            f'<option value="{outsider.pk}">{outsider}</option>'
        )

    def test_merge_person(self):
        "Create two people, destructively merge second into the first."
        club = factories.ClubFactory.create()

        # Not using the PersonFactory because it requires a User, we want a
        # bare Person instance without that relationship.
        member1 = club.members.create(first_name="Alice", last_name="User")

        # Our second Person should have the User property, because we want to
        # transfer that to the first.
        member2 = factories.PersonFactory.create(club=club)

        # Check our initial setup is as we expect.
        self.assertCountEqual(
            [
                ("Alice", "User", None),
                (member2.first_name, member2.last_name, member2.user.pk),
            ],
            club.members.values_list("first_name", "last_name", "user"),
        )

        # Exercise the merge view.
        with self.login(self.superuser):
            data = {
                "first_name": "Alice",
                "last_name": "User",
                "gender": "F",
                "date_of_birth": "1983-04-27",
                "email": "",
                "home_phone": "",
                "work_phone": "",
                "mobile_phone": "",
                "user": "",
                "merge": member2.pk,
                "keep_old": "false",
            }
            self.post("admin:fixja:club:person:merge", club.pk, member1.pk, data=data)
            self.response_302()

        # Check the database state after the merge.
        self.assertCountEqual(
            [
                ("Alice", "User", member2.user.pk, "F", date(1983, 4, 27)),
            ],
            club.members.values_list(
                "first_name", "last_name", "user", "gender", "date_of_birth"
            ),
        )

    def test_transfer_person(self):
        """Test transferring a person from one club to another."""
        original_club = factories.ClubFactory.create(title="Original Club")
        target_club = factories.ClubFactory.create(title="Target Club")

        # Create a person with team associations
        person = factories.PersonFactory.create(
            club=original_club, first_name="Transfer", last_name="Test"
        )

        # Create a team association to ensure it's preserved after transfer
        division = factories.DivisionFactory.create()
        division.season.competition.clubs.add(original_club, target_club)
        team = factories.TeamFactory.create(club=original_club, division=division)
        team_association = factories.TeamAssociationFactory.create(
            team=team, person=person
        )

        # Verify initial state
        self.assertEqual(person.club, original_club)
        self.assertEqual(team_association.person, person)

        # Test the transfer view requires login
        self.assertLoginRequired(
            "admin:fixja:club:person:transfer", original_club.pk, person.pk
        )

        with self.login(self.superuser):
            # Test GET request shows the form
            self.get("admin:fixja:club:person:transfer", original_club.pk, person.pk)
            self.response_200()

            # Test POST request transfers the person
            data = {"club": target_club.pk}
            self.post(
                "admin:fixja:club:person:transfer",
                original_club.pk,
                person.pk,
                data=data,
            )
            self.response_302()

            # Verify the person was transferred
            person.refresh_from_db()
            self.assertEqual(person.club, target_club)

            # Verify team association is preserved
            team_association.refresh_from_db()
            self.assertEqual(team_association.person, person)
            self.assertEqual(team_association.team, team)

    def test_edit_clubassociation(self):
        association = factories.ClubAssociationFactory.create()
        self.assertLoginRequired(
            "admin:fixja:club:clubassociation:add", association.club.pk
        )
        self.assertLoginRequired(
            "admin:fixja:club:clubassociation:edit", association.club.pk, association.pk
        )
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:club:clubassociation:add", association.club.pk
            )
            self.assertGoodView(
                "admin:fixja:club:clubassociation:edit",
                association.club.pk,
                association.pk,
            )

    # def test_delete_competition(self):
    #     self.assertLoginRequired('admin:fixja:competition:delete', 1)
    #     with self.login(username='gary@touch.asn.au'):
    #         self.get('admin:fixja:competition:delete', 1)
    #         self.response_405()
    #         self.post('admin:fixja:competition:delete', 1)
    #         self.response_302()

    def test_perms_views(self):
        team = factories.TeamFactory.create()

        perms_competition = team.division.season.competition.url_names["perms"]
        self.assertLoginRequired(perms_competition.url_name, *perms_competition.args)

        perms_season = team.division.season.url_names["perms"]
        self.assertLoginRequired(perms_season.url_name, *perms_season.args)

        # perms_division = team.division.url_names["perms"]
        # self.assertLoginRequired(perms_division.url_name, *perms_division.args)

        perms_team = team.url_names["perms"]
        self.assertLoginRequired(perms_team.url_name, *perms_team.args)

        with self.login(self.superuser):
            self.assertGoodView(perms_competition.url_name, *perms_competition.args)
            self.assertGoodView(perms_season.url_name, *perms_season.args)
            # self.assertGoodView(perms_division.url_name, *perms_division.args)
            self.assertGoodView(
                perms_team.url_name,
                *perms_team.args,
                test_query_count=100,
            )

    def test_registration_form(self):
        club = factories.ClubFactory.create()
        team = factories.TeamFactory.create(club=club)
        team.division.season.competition.clubs.add(club)
        self.assertLoginRequired(
            "admin:fixja:club:registration-form",
            club.pk,
            team.division.season.pk,
            "html",
        )
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:club:registration-form",
                club.pk,
                team.division.season.pk,
                "html",
            )

    def test_officials(self):
        club = factories.ClubFactory.create()
        season = factories.SeasonFactory.create()
        season.competition.clubs.add(club)
        with self.login(self.superuser):
            self.get("admin:fixja:club:officials", club.pk, season.pk)
            self.response_200()
            self.assertResponseContains(
                by_shell(
                    workbook='<p class="wb-empty" data-wb-formset-none>'
                    "There are no officials of this club.</p>",
                    explorer='<td colspan="3" class="empty-state">'
                    "The club has no officials for this season yet.</td>",
                ),
                html=by_shell(workbook=False, explorer=True),
            )

    def test_officials_complete_season_is_read_only_to_club_administrators(self):
        club = factories.ClubFactory.create()
        season = factories.SeasonFactory.create(complete=True)
        season.competition.clubs.add(club)
        user = UserFactory.create(is_staff=True)
        with self.login(user):
            self.get("admin:fixja:club:officials", club.pk, season.pk)
            self.response_200()
            self.assertResponseContains(
                by_shell(
                    workbook='<tr class="wb-table-empty"><td colspan="2">'
                    "There are no club officials for this season.</td></tr>",
                    explorer='<td colspan="2" class="empty-state">'
                    "The club has no officials for this season.</td>",
                ),
                html=by_shell(workbook=False, explorer=True),
            )

    def test_officials_save_returns_to_the_club(self):
        club = factories.ClubFactory.create()
        season = factories.SeasonFactory.create()
        season.competition.clubs.add(club)
        person = factories.PersonFactory.create(club=club)
        role = factories.ClubRoleFactory.create(competition=season.competition)
        with self.login(self.superuser):
            self.post(
                "admin:fixja:club:officials",
                club.pk,
                season.pk,
                data={
                    "form-TOTAL_FORMS": "1",
                    "form-INITIAL_FORMS": "0",
                    "form-MIN_NUM_FORMS": "",
                    "form-MAX_NUM_FORMS": "1000",
                    "form-0-person": person.pk,
                    "form-0-roles": role.pk,
                },
            )
            self.response_302()
            self.assertRedirects(
                self.last_response,
                reverse("admin:fixja:club:edit", args=(club.pk,)),
                fetch_redirect_response=False,
            )
        official = SeasonAssociation.objects.get(club=club, season=season)
        self.assertEqual(official.person, person)
        self.assertEqual(list(official.roles.all()), [role])

    def test_team_members_save_returns_to_the_club(self):
        club = factories.ClubFactory.create()
        team = factories.TeamFactory.create(club=club)
        season = team.division.season
        season.competition.clubs.add(club)
        person = factories.PersonFactory.create(club=club)
        role = factories.TeamRoleFactory.create(competition=season.competition)
        with self.login(self.superuser):
            self.post(
                "admin:fixja:club:team:edit",
                club.pk,
                season.pk,
                team.pk,
                data={
                    "people-TOTAL_FORMS": "1",
                    "people-INITIAL_FORMS": "0",
                    "people-MIN_NUM_FORMS": "",
                    "people-MAX_NUM_FORMS": "1000",
                    "people-0-number": "7",
                    "people-0-person": person.pk,
                    "people-0-is_player": "1",
                    "people-0-roles": role.pk,
                },
            )
            self.response_302()
            self.assertRedirects(
                self.last_response,
                reverse("admin:fixja:club:edit", args=(club.pk,)),
                fetch_redirect_response=False,
            )
        member = TeamAssociation.objects.get(team=team)
        self.assertEqual(member.person, person)
        self.assertEqual(member.number, 7)
        self.assertEqual(list(member.roles.all()), [role])

    @unittest.expectedFailure
    def test_edit_team_members(self):
        club = factories.ClubFactory.create()
        team = factories.TeamFactory.create(club=club)
        self.assertLoginRequired(
            "admin:fixja:club:team:edit", club.pk, team.division.season.pk, team.pk
        )
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:club:team:edit", club.pk, team.division.season.pk, team.pk
            )


@per_shell
class RegistrationFormTests(TestCase):
    """
    A club's registration form for a season: a sheet for each of its teams,
    with the team's staff and players, as HTML or as a PDF.
    """

    def setUp(self):
        super().setUp()
        self.club = factories.ClubFactory.create()
        self.team = factories.TeamFactory.create(club=self.club, title="Marlins")
        self.season = self.team.division.season
        self.season.competition.clubs.add(self.club)

    def test_html(self):
        """
        The sheet names the team (#464), its staff by their names and not the
        repr of their bytes (#463), and its players.
        """
        coach = factories.TeamAssociationFactory.create(
            team=self.team,
            is_player=False,
            person=factories.PersonFactory.create(
                club=self.club, user__first_name="Staffy", user__last_name="McStaff"
            ),
        )
        coach.roles.add(
            factories.TeamRoleFactory.create(
                competition=self.season.competition, name="Coach"
            )
        )
        factories.TeamAssociationFactory.create(
            team=self.team,
            number=7,
            person=factories.PersonFactory.create(
                club=self.club,
                user__first_name="Playa",
                user__last_name="McPlay",
                date_of_birth=date(2002, 12, 25),
                email="playa@example.com",
            ),
        )
        with self.login(self.superuser):
            self.get(
                "admin:fixja:club:registration-form",
                self.club.pk,
                self.season.pk,
                "html",
            )
        self.assert_http_200_ok()
        self.assertResponseContains(
            self.by_shell(
                workbook='<div class="rf-team team">Marlins</div>',
                explorer="<h2>Marlins</h2>",
            )
        )
        self.assertResponseContains(
            '<tr><th rowspan="1">Coach</th><td>Staffy McStaff</td></tr>'
        )
        self.assertResponseContains(
            self.by_shell(
                workbook=(
                    "<tr><td>7</td><td>Playa</td><td>McPlay</td><td>25/12/2002</td>"
                    '<td>playa@example.com</td><td class="signature"></td></tr>'
                ),
                explorer=(
                    '<tr><td class="num">7</td><td>Playa</td><td>McPlay</td>'
                    "<td>25/12/2002</td><td>playa@example.com</td>"
                    '<td class="signature"></td></tr>'
                ),
            )
        )

    @override_settings(PRINCE_SERVER="pdf.example.com")
    def test_pdf(self):
        """
        The PDF server gets the form's HTML, not the repr of the bytes the
        rendered form holds (#438), and the view answers with the PDF.
        """
        with self.login(self.superuser), responses.RequestsMock() as pdf_service:
            pdf_service.post("https://pdf.example.com/", body=b"%PDF-1.4 fake")
            self.get(
                "admin:fixja:club:registration-form",
                self.club.pk,
                self.season.pk,
                "pdf",
            )
            # The calls are cleared when the mock is stopped.
            self.assertEqual(
                pdf_service.calls[0].request.body[:15], b"<!DOCTYPE html>"
            )
        self.assert_http_200_ok()
        self.assertResponseHeaders({"Content-Type": "application/pdf"})
        self.assertEqual(self.last_response.content, b"%PDF-1.4 fake")

    #: The HTML form's queries, however many teams and people it lists (#470):
    #: the teams with their divisions, the players, the staff and the staff's
    #: roles are a query each.
    QUERIES = 16

    def add_people(self, *teams):
        """Give each team three players, and two staff with two roles each."""
        roles = factories.TeamRoleFactory.create_batch(
            2, competition=self.season.competition
        )
        for team in teams:
            factories.TeamAssociationFactory.create_batch(
                3, team=team, person__club=self.club
            )
            for staff in factories.TeamAssociationFactory.create_batch(
                2, team=team, is_player=False, person__club=self.club
            ):
                staff.roles.add(*roles)

    def assertQueries(self):
        with self.login(self.superuser), self.assertNumQueries(self.QUERIES):
            self.get(
                "admin:fixja:club:registration-form",
                self.club.pk,
                self.season.pk,
                "html",
            )
        self.assert_http_200_ok()

    def test_queries_one_team(self):
        self.add_people(self.team)
        self.assertQueries()

    def test_queries_three_teams(self):
        self.add_people(
            self.team,
            *(
                factories.TeamFactory.create(
                    club=self.club, division=self.team.division, title=title
                )
                for title in ("Dolphins", "Sharks")
            ),
        )
        self.assertQueries()


class BackendTests(MessagesTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.login(self.superuser)

    def test_add_division(self):
        """
        Using the admin interface, add a new division and check that it appears
        in the front-end. Later update the form data and repost to ensure the
        front-end is also updated.
        """
        season = factories.SeasonFactory.create()
        data = {
            "title": "Mixed 4",
            "short_title": "X4",
            "points_formula_0": "3",
            "points_formula_1": "2",
            "points_formula_2": "1",
            "points_formula_3": "",
            "points_formula_4": "",
            "points_formula_5": "",
            "forfeit_for_score": "5",
            "forfeit_against_score": "0",
            "include_forfeits_in_played": "1",
            "color": "#ff5733",  # Add color field since it's now mandatory
            "slug": "",
            "slug_locked": "0",
        }
        add_division = Division(season=season).url_names["add"]
        self.post(add_division.url_name, *add_division.args, data=data)
        self.response_302()

        with self.settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls"):
            self.assertGoodView(
                "competition:season", season.competition.slug, season.slug
            )
            self.assertResponseContains("Mixed 4", html=False)
            self.assertGoodView(
                "competition:division", season.competition.slug, season.slug, "mixed-4"
            )
            self.assertResponseContains("Mixed 4", html=False)

        data.update(
            {
                "title": "4th Division Mixed",
            }
        )
        division = season.divisions.latest("pk")

        edit_division = division.url_names["edit"]
        self.post(edit_division.url_name, *edit_division.args, data=data)
        self.response_302()

        with self.settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls"):
            self.assertGoodView(
                "competition:season", season.competition.slug, season.slug
            )
            self.assertResponseNotContains("Mixed 4", html=False)
            self.assertResponseContains("4th Division Mixed", html=False)

    def test_scorers_view_basic(self):
        """Test that scorers view loads correctly with basic match and statistics data"""
        # Create basic structure
        stage = factories.StageFactory.create()
        division = stage.division

        # Create teams and players
        team = factories.TeamFactory.create(division=division)
        person = factories.PersonFactory.create(club=team.club)

        # Create team association
        factories.TeamAssociationFactory.create(team=team, person=person)

        # Create a match
        match = factories.MatchFactory.create(
            stage=stage,
            home_team=team,
            away_team=factories.TeamFactory.create(division=division),
        )

        # Create match statistics for the player
        SimpleScoreMatchStatistic.objects.create(
            match=match, player=person, played=1, points=10, mvp=2
        )

        # Test the scorers view
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:season:division:scorers",
                division.season.competition.pk,
                division.season.pk,
                division.pk,
            )
            self.response_200()

        # Get context data directly
        scorers = self.get_context("scorers")
        mvp = self.get_context("mvp")

        # Expected data structure from Django ORM values()
        expected_scorer = {
            "uuid": person.uuid,
            "first_name": person.first_name,
            "last_name": person.last_name,
            "club__title": team.club.title,
            "played": 1,
            "points": 10,
            "mvp": 2,
        }

        # Assert direct equality with expected data
        self.assertEqual([expected_scorer], list(scorers))
        self.assertEqual([expected_scorer], list(mvp))

        # Assert HTML structure contains the expected table rows
        def row(total):
            return by_shell(
                workbook=(
                    '<tr><td class="wb-num">1</td>'  # rank
                    f'<th scope="row">{person.first_name} {person.last_name}</th>'
                    f"<td>{team.club.title}</td>"
                    '<td class="wb-num">1</td>'  # played
                    f'<td class="wb-num"><strong>{total}</strong></td></tr>'
                ),
                explorer=(
                    '<tr><td class="num muted">1</td>'  # place
                    f"<td>{person.first_name} {person.last_name}</td>"
                    f'<td class="wide-only">{team.club.title}</td>'
                    '<td class="num">1</td>'  # played
                    f'<td class="num strong">{total}</td></tr>'
                ),
            )

        expected_scorer_row = row(10)  # points
        expected_mvp_row = row(2)  # votes

        self.assertResponseContains(expected_scorer_row)
        self.assertResponseContains(expected_mvp_row)

    def test_update_club(self):
        """
        Using the admin interface, update an existing Club and ensure that the
        revised attribute is correctly updated.
        """
        club = factories.ClubFactory.create()
        data = {
            "title": "Bare Back Riders",
            "short_title": "",
            "abbreviation": "BBR",
            "website": "",
            "twitter": "",
            "primary": "",
            "status": "active",
            "slug": "bare-back-riders",
            "slug_locked": "0",
        }
        self.post("admin:fixja:club:edit", club.pk, data=data)
        self.response_302()

        self.get("admin:fixja:club:list")
        self.assertResponseContains("Bare Back Riders", html=False)
        self.assertResponseContains("BBR", html=False)

    def test_match_detail(self):
        play_at = factories.GroundFactory.create()
        m = factories.MatchFactory.create(
            play_at=play_at, home_team_score=3, away_team_score=0
        )

        # Make sure home team has some players associated with it.
        factories.TeamAssociationFactory.create_batch(
            4, is_player=True, team=m.home_team, person__club=m.home_team.club
        )

        kwargs = {
            "match_id": m.pk,
            "stage_id": m.stage_id,
            "division_id": m.stage.division_id,
            "season_id": m.stage.division.season_id,
            "competition_id": m.stage.division.season.competition_id,
        }
        url = reverse(
            "admin:competition:competition:season:division:stage:match:detail",
            kwargs=kwargs,
        )

        res = self.client.get(url)

        # After GET ensure away_team has no players
        text = by_shell(
            workbook="""
        <tr class="wb-table-empty"><td colspan="5">
            There are no registered players in this team.
        </td></tr>
        """,
            explorer="""
        <td colspan="5" class="empty-state">
            No player is registered in this team.
        </td>
        """,
        )
        self.assertResponseContains(text, res)

        data = {
            "home-0-number": "3",
            "home-0-id": "",
            "home-0-played": "1",
            "home-0-points": "0",
            "home-0-mvp": "0",
            "home-1-number": "8",
            "home-1-id": "",
            "home-1-played": "1",
            "home-1-points": "0",
            "home-1-mvp": "0",
            "home-2-number": "10",
            "home-2-id": "",
            "home-2-played": "1",
            "home-2-points": "0",
            "home-2-mvp": "0",
            "home-3-number": "12",
            "home-3-id": "",
            "home-3-played": "1",
            "home-3-points": "0",
            "home-3-mvp": "0",
            "home-TOTAL_FORMS": "4",
            "home-INITIAL_FORMS": "4",
            "home-MAX_NUM_FORMS": "1000",
            "away-TOTAL_FORMS": "0",
            "away-INITIAL_FORMS": "0",
            "away-MAX_NUM_FORMS": "1000",
        }

        res = self.client.post(url, data=data)
        text = by_shell(
            workbook="""
        <div class="wb-problems" role="alert"><ul>
            <li>
                Total number of points (0) does not equal total
                number of scores (3) for this team.
            </li>
        </ul></div>
        """,
            explorer="""
        <div class="form-errors" role="alert">
            <svg class="icon" aria-hidden="true" focusable="false">
                <use href="/static/touchtechnology/admin/explorer/img/icons.svg#alert"></use>
            </svg>
            <ul>
                <li>
                    Total number of points (0) does not equal total
                    number of scores (3) for this team.
                </li>
            </ul>
        </div>
        """,
        )
        self.assertResponseContains(text, res)

        data.update(
            {
                "home-0-points": "0",
                "home-1-points": "1",
                "home-2-points": "0",
                "home-3-points": "2",
            }
        )
        res = self.client.post(url, data=data)
        self.assertRedirects(res, reverse("admin:index"))

        # Make sure the database is correctly reflecting the detailed entries.
        self.assertEqual(m.statistics.count(), 4)

    def test_bug_0068(self):
        """
        While there are no LadderEntry or LadderSummary records for matches
        revealed in the ``match-results`` view, the submission worked fine.

        However on subsequent processing the method decorator is invoked
        differently, and there is now "raw" keyword argument - this resulted
        in issue #68.
        """
        match = factories.MatchFactory.create()
        data = {
            # first formset
            "matches-INITIAL_FORMS": "1",
            "matches-MAX_NUM_FORMS": "1000",
            "matches-TOTAL_FORMS": "1",
            "matches-0-id": str(match.pk),
            "matches-0-home_team_score": "4",
            "matches-0-away_team_score": "3",
            "matches-0-is_forfeit": "0",
            # second formset
            "byes-INITIAL_FORMS": "0",
            "byes-MAX_NUM_FORMS": "1000",
            "byes-TOTAL_FORMS": "0",
        }

        self.post(
            "admin:fixja:match-results",
            match.stage.division.season.competition.pk,
            match.stage.division.season.pk,
            match.date.strftime("%Y%m%d"),
            data=data,
        )
        self.response_302()

        data.update(
            {
                "matches-1-home_team_score": "5",
                "matches-1-away_team_score": "2",
            }
        )
        self.post(
            "admin:fixja:match-results",
            match.stage.division.season.competition.pk,
            match.stage.division.season.pk,
            match.date.strftime("%Y%m%d"),
            data=data,
        )
        self.response_302()

    def test_enhancement_0024_team(self):
        """
        When editing a Team or UndecidedTeam it should be possible to delete
        the object if there are no matches that team has been assigned to.
        """
        stage = factories.StageFactory.create()
        home = factories.TeamFactory.create(division=stage.division)
        away = factories.UndecidedTeamFactory.create(stage=stage)

        factories.MatchFactory.create(
            stage=stage, home_team=home, away_team=None, away_team_undecided=away
        )

        edit_home = home.url_names["edit"]
        delete_home = home.url_names["delete"]
        delete_url = home.urls["delete"]

        # Ensure the edit view response does not include a delete button.
        self.get(edit_home.url_name, *edit_home.args)
        self.assertResponseNotContains(delete_url, html=False)

        # Ensure that visiting the delete view does not respond when matches
        # are associated with the Team.
        self.get(delete_home.url_name, *delete_home.args)
        self.response_410()

        # Ensure that POST to the delete view fails the same as for GET.
        self.post(delete_home.url_name, *delete_home.args)
        self.response_410()

        # Create a new Team and re-check the scenarios.
        team = factories.TeamFactory.create(division=stage.division)

        edit_team = team.url_names["edit"]
        delete_team = team.url_names["delete"]
        delete_url = team.urls["delete"]

        # Ensure the edit view response does not include a delete button.
        self.get(edit_team.url_name, *edit_team.args)
        self.assertResponseNotContains(delete_url, html=False)

        # Ensure that visiting the delete view is not allowed when there are no
        # matches but you use a GET request.
        self.get(delete_team.url_name, *delete_team.args)
        self.response_405()

        # Ensure that POST to the delete view redirects.
        self.post(delete_team.url_name, *delete_team.args)
        self.response_302()

        # Subsequent GET request to the edit view should be a 404.
        self.get(edit_team.url_name, *edit_team.args)
        self.response_404()

    def test_enhancement_0024_undecidedteam(self):
        """
        When editing a Team or UndecidedTeam it should be possible to delete
        the object if there are no matches that team has been assigned to.
        """
        stage = factories.StageFactory.create()
        home = factories.TeamFactory.create(division=stage.division)
        away = factories.UndecidedTeamFactory.create(stage=stage)

        factories.MatchFactory.create(
            stage=stage, home_team=home, away_team=None, away_team_undecided=away
        )

        delete_url = self.reverse(
            away._get_admin_namespace() + ":delete", *away._get_url_args()
        )

        # Ensure the edit view response does not include a delete button.
        self.get(away._get_admin_namespace() + ":edit", *away._get_url_args())
        self.assertResponseNotContains(delete_url, html=False)

        # Ensure that visiting the delete view does not respond when matches
        # are associated with the Team.
        self.get(away._get_admin_namespace() + ":delete", *away._get_url_args())
        self.response_410()

        # Ensure that POST to the delete view fails the same as for GET.
        self.post(away._get_admin_namespace() + ":delete", *away._get_url_args())
        self.response_410()

        # Create a new UndecidedTeam and re-check the scenarios.
        team = factories.UndecidedTeamFactory.create(stage=stage)

        delete_url = self.reverse(
            team._get_admin_namespace() + ":delete", *team._get_url_args()
        )

        # Ensure the edit view response *does* include a delete button.
        self.get(stage._get_admin_namespace() + ":edit", *stage._get_url_args())
        self.assertResponseContains(delete_url, html=False)

        # Ensure that visiting the delete view is not allowed when there are no
        # matches but you use a GET request.
        self.get(team._get_admin_namespace() + ":delete", *team._get_url_args())
        self.response_405()

        # Ensure that POST to the delete view redirects.
        self.post(team._get_admin_namespace() + ":delete", *team._get_url_args())
        self.response_302()

        # Subsequent GET request to the edit view should be a 404.
        self.get(team._get_admin_namespace() + ":delete", *team._get_url_args())
        self.response_404()

    def test_bug_80_add_stagegroup(self):
        "Add Pool should gain order equal to max(order) + 1"
        pool = factories.StageGroupFactory.create()
        data = {
            "title": "Group Z",
            "short_title": "",
            "slug": "",
            "slug_locked": "0",
            "carry_ladder": "0",
        }
        add_pool = pool.url_names["add"]
        self.post(add_pool.url_name, *add_pool.args[:-1], data=data)
        self.response_302()
        z = pool.stage.pools.latest("order")
        self.assertEqual(z.order, pool.order + 1)

    def test_bug_0115_add_duplicate_team_name(self):
        """
        When adding two teams to the same division, it should not allow the
        second one because of database integrity constraints.
        """
        team = factories.TeamFactory.create()
        data = {"title": team.title}
        add_team = team.url_names["add"]
        self.post(add_team.url_name, *add_team.args[:-1], data=data)
        form = self.get_context("form")
        self.assertFormError(form, "title", ["Team with this Title already exists."])

    def test_team_add(self):
        division = factories.DivisionFactory.create()
        data = {
            "title": "New Team",
            "short_title": "",
            "names_locked": "0",
            "timeslots_after": "",
            "timeslots_before": "",
            "team_clashes": [],
        }
        # Unsaved instance means we don't have to trim the final positional argument.
        add_team = Team(division=division).url_names["add"]
        self.post(add_team.url_name, *add_team.args, data=data)
        self.response_302()
        # Ensure that the team was created and that it has a slug
        team = division.teams.get(title="New Team")
        self.assertEqual(team.slug, "new-team")

    def test_team_edit(self):
        team = factories.TeamFactory.create()
        data = {
            "title": "Blue",
            "short_title": "",
            "names_locked": "0",
            "timeslots_after": "19:20",  # new value
            "timeslots_before": "",
            "team_clashes": [],
        }

        edit_team = team.url_names["edit"]
        self.post(edit_team.url_name, *edit_team.args, data=data)
        self.response_302()

        # Ensure that the team was updated
        blue = Team.objects.get(title="Blue")
        self.assertEqual(team.pk, blue.pk)
        self.assertEqual(blue.slug, "blue")
        self.assertEqual(blue.timeslots_after, time(19, 20))

        # Try again, update the title and make sure the slug changes
        data["title"] = "Magenta"
        edit_blue = blue.url_names["edit"]
        self.post(edit_blue.url_name, *edit_blue.args, data=data)
        self.response_302()

        magenta = Team.objects.get(title="Magenta")
        self.assertEqual(team.pk, magenta.pk)
        self.assertEqual(magenta.slug, "magenta")
        self.assertEqual(magenta.timeslots_after, time(19, 20))

    def test_add_stage_duplicate_slug(self):
        """
        When adding a new stage to a division it should not be possible to add
        a second stage with a slug already used because of database integrity
        constraints.
        """
        stage = factories.StageFactory.create()
        data = {"title": stage.title}
        add_stage = stage.url_names["add"]
        self.post(add_stage.url_name, *add_stage.args[:-1], data=data)
        form = self.get_context("form")
        self.assertFormError(form, "title", ["Stage with this Title already exists."])

    def test_bug_85_add_match_season_live_stream(self):
        """
        When the Season is set to live stream, the Match form changes.

        The ability to manually add a match under this configuration should be possible,
        but there is a bug caused by accessing unset relations.

        Refs: https://github.com/goodtune/vitriolic/issues/85
        """
        stage = factories.StageFactory.create(division__season__live_stream=True)
        team1 = factories.TeamFactory.create(division=stage.division)
        team2 = factories.TeamFactory.create(division=stage.division)
        data = {
            "home_team": team1.pk,
            "away_team": team2.pk,
            "label": "",
            "round": 1,
            "date": "2025-04-28",
            "include_in_ladder": "0",
            "live_stream": "0",
            "live_stream_thumbnail_image-clear": "0",
        }
        # Unsaved instance means we don't have to trim the final positional argument.
        add_match = Match(stage=stage).url_names["add"]
        data["live_stream_thumbnail_image"] = ""
        self.post(add_match.url_name, *add_match.args, data=data)
        self.response_302()

    def test_bug_100_add_stagegroup(self):
        """
        Adding a Pool (StageGroup) should not fail to render.
        """
        stage = factories.StageFactory.create()
        add_pool = StageGroup(stage=stage).url_names["add"]
        self.get_check_200(add_pool.url_name, *add_pool.args)

    def test_edit_match_referee_appointments(self):
        """
        Test that referee appointments work correctly with and without live streaming
        enabled at the division or match level.
        """
        # Create a season with live streaming disabled and no YouTube config
        stage = factories.StageFactory.create(
            title="Test Stage",
            division__title="Test Division",
            division__season__title="Test Season",
            division__season__live_stream=False,
            division__season__live_stream_project_id=None,
            division__season__live_stream_client_id=None,
            division__season__live_stream_client_secret=None,
        )

        referees = factories.SeasonRefereeFactory.create_batch(
            3,
            season=stage.division.season,
            person__last_name="Referee",
        )

        match = factories.MatchFactory.create(
            stage=stage,
            home_team__title="Home Team",
            home_team__division=stage.division,
            away_team__title="Away Team",
            away_team__division=stage.division,
            date=date(2025, 5, 1),
            include_in_ladder=True,
        )

        referee_appointments_view = match.url_names["referees"]

        for season_stream, match_stream, referee in [
            (False, False, 0),
            (True, False, 1),
            (True, True, 2),
        ]:
            with self.subTest(season_stream=season_stream, match_stream=match_stream):
                stage.division.season.live_stream = season_stream
                stage.division.season.save()

                match.live_stream = match_stream
                match.videos = ["http://example.com/"] if match_stream else []
                match.referees.set([])
                match.save()

                self.post(
                    referee_appointments_view.url_name,
                    *referee_appointments_view.args,
                    data={
                        "home_team": match.home_team.pk,
                        "away_team": match.away_team.pk,
                        "referees": [referees[referee].pk],
                    },
                )
                self.assertRedirects(self.last_response, stage.urls["edit"])
                self.assertCountEqual(
                    match.referees.values_list("person__first_name", flat=True),
                    [referees[referee].person.first_name],
                )

    def test_bug_116_add_ground(self):
        """
        Adding a Ground to a Venue in a Season with live_stream=True should not fail.
        """
        venue = factories.VenueFactory.create(season__live_stream=True)
        add_ground = Ground(venue=venue).url_names["add"]
        self.get_check_200(add_ground.url_name, *add_ground.args)
        data = {
            "title": "Test Ground",
            "short_title": "",
            "abbreviation": "",
            "timezone": "Australia/Brisbane",
            "latlng_0": "-27.470125",
            "latlng_1": "153.021072",
            "latlng_2": "0",
            "slug": "test-ground",
            "slug_locked": "0",
            "live_stream": "0",
        }
        self.post(add_ground.url_name, *add_ground.args, data=data)
        self.assertRedirects(self.last_response, venue.urls["edit"])

    def test_delete_division_with_protected_objects(self):
        """
        Test that deleting a division with related protected objects shows a user-friendly error.
        """
        # Create division with protected related objects
        division = factories.DivisionFactory.create()
        stage = factories.StageFactory.create(division=division, title="Test Stage")
        team = factories.TeamFactory.create(division=division, title="Test Team")

        # Try to delete the division
        delete_division = division.url_names["delete"]
        self.post(delete_division.url_name, *delete_division.args)

        # Should redirect back to the division edit page with error message
        self.assertRedirects(self.last_response, division.urls["edit"])

        # Check that objects still exists
        self.assertQuerySetEqual(Division.objects.all(), [division])
        self.assertQuerySetEqual(Stage.objects.all(), [stage])
        self.assertQuerySetEqual(Team.objects.all(), [team])

        # Check that error message was set
        self.assertMessages(
            self.last_response,
            [
                messages.Message(
                    level=messages.ERROR,
                    message=(
                        f'Cannot delete {division._meta.verbose_name} "{division.title}" '
                        f"because it is still referenced by: "
                        f"1 stage: {stage.title}; 1 team: {team.title}. "
                        "Please delete or move these related objects first."
                    ),
                )
            ],
        )

    def test_delete_division_without_protected_objects(self):
        """
        Test that deleting a division without related objects works normally.
        """
        # Create division without any related objects
        division = factories.DivisionFactory.create()
        season = division.season

        # Try to delete the division
        delete_division = division.url_names["delete"]
        self.post(delete_division.url_name, *delete_division.args)

        # Should redirect back to season page
        self.assertRedirects(self.last_response, season.urls["edit"] + "#divisions-tab")

        # Check that division was deleted
        self.assertQuerySetEqual(Division.objects.all(), [])

        # Check that success message was displayed
        self.assertMessages(
            self.last_response,
            [
                messages.Message(
                    level=messages.SUCCESS,
                    message=f"The {division._meta.verbose_name} has been deleted.",
                )
            ],
        )

    def test_delete_stage_with_protected_objects(self):
        """
        Test that deleting a stage with related protected objects (Pools) shows a user-friendly error.
        This demonstrates the generic ProtectedError handling works for different model types.
        """
        # Create stage with protected related objects (Pool)
        stage = factories.StageFactory.create(title="Test Stage")
        pool = factories.StageGroupFactory.create(stage=stage, title="Test Pool")

        # Try to delete the stage
        delete_stage = stage.url_names["delete"]
        self.post(delete_stage.url_name, *delete_stage.args)

        # Should redirect back to the stage edit page with error message
        self.assertRedirects(self.last_response, stage.urls["edit"])

        # Check that objects still exists
        self.assertQuerySetEqual(Stage.objects.all(), [stage])
        self.assertQuerySetEqual(StageGroup.objects.all(), [pool])

        # Check that error message was set
        self.assertMessages(
            self.last_response,
            [
                messages.Message(
                    level=messages.ERROR,
                    message=(
                        f'Cannot delete {stage._meta.verbose_name} "{stage.title}" because '
                        f"it is still referenced by: 1 pool: {pool.title}. "
                        "Please delete or move these related objects first."
                    ),
                )
            ],
        )

    def test_draw_generation_wizard_empty_form_bug(self):
        """
        Test that the draw generation wizard doesn't crash with TypeError when
        accessing formset.empty_form.media in the template.

        This reproduces the bug from issue #133 where DrawGenerationForm.__init__()
        was missing 1 required positional argument: 'initial'
        """
        # Create a Stage
        stage = factories.StageFactory.create(
            division__season__mode=DAILY,
            division__games_per_day=1,
        )

        # Create a batch of four Teams in the Division
        teams = factories.TeamFactory.create_batch(4, division=stage.division)

        # Establish the expected matches for the teams using a round-robin format
        matches = round_robin(teams)

        # Create a DrawFormat that will put each team against each other once
        draw_format = factories.DrawFormatFactory.create(
            name="Round Robin (4 teams)",
            text=round_robin_format([1, 2, 3, 4]),
            teams=4,
        )

        # Attempt to build the draw using the Wizard
        build_url = stage.url_names["build"]

        # This should not raise TypeError anymore
        with self.login(self.superuser):
            # Step 0: Test that the first step renders without error
            self.get(build_url.url_name, *build_url.args)
            self.response_200()

            # Extract the formset from the context and test empty_form works
            formset = self.get_context("form")
            self.assertIsNotNone(formset)

            # This should not raise TypeError - the main bug we're testing
            empty_form = formset.empty_form
            self.assertIsNotNone(empty_form)

            # Test media property access (this was the original failing case)
            media = empty_form.media
            self.assertIsNotNone(media)

            # Prepare step 0 data with a valid DrawFormat selection and date
            step0_data = {
                # Wizard management form data
                "draw_generation_wizard-current_step": "0",
            }

            # Formset management form data
            step0_data.update(
                {
                    "0-TOTAL_FORMS": "1",
                    "0-INITIAL_FORMS": "1",
                    "0-MIN_NUM_FORMS": "0",
                    "0-MAX_NUM_FORMS": "1000",
                    # Form 0 data
                    "0-0-start_date": "2025-07-15",
                    "0-0-format": draw_format.pk,
                    "0-0-rounds": "",
                    "0-0-offset": "",
                }
            )

            # Submit step 0 to proceed to step 1
            self.post(build_url.url_name, *build_url.args, data=step0_data)
            self.response_200()

            # Step 1: Test the second step
            formset = self.get_context("form")
            self.assertIsNotNone(formset)

            # Test that empty_form works on step 1 - this is the main fix
            empty_form = formset.empty_form
            self.assertIsNotNone(empty_form)

            # Test that we can access the media property without TypeError
            media = empty_form.media
            self.assertIsNotNone(media)

            # Prepare step 1 data
            step1_data = {
                "draw_generation_wizard-current_step": "1",
                "1-TOTAL_FORMS": "6",
                "1-INITIAL_FORMS": "6",
                "1-MIN_NUM_FORMS": "0",
                "1-MAX_NUM_FORMS": "1000",
                # Form 1 data
                "1-0-round": "1",
                "1-0-home_team": matches[0][0][0].pk,
                "1-0-away_team": matches[0][0][1].pk,
                "1-0-date": "2025-07-15",
                # Form 2 data
                "1-1-round": "1",
                "1-1-home_team": matches[0][1][0].pk,
                "1-1-away_team": matches[0][1][1].pk,
                "1-1-date": "2025-07-15",
                # Form 3 data
                "1-2-round": "2",
                "1-2-home_team": matches[1][0][0].pk,
                "1-2-away_team": matches[1][0][1].pk,
                "1-2-date": "2025-07-16",
                # Form 4 data
                "1-3-round": "2",
                "1-3-home_team": matches[1][1][0].pk,
                "1-3-away_team": matches[1][1][1].pk,
                "1-3-date": "2025-07-16",
                # Form 5 data
                "1-4-round": "3",
                "1-4-home_team": matches[2][0][0].pk,
                "1-4-away_team": matches[2][0][1].pk,
                "1-4-date": "2025-07-17",
                # Form 6 data
                "1-5-round": "3",
                "1-5-home_team": matches[2][1][0].pk,
                "1-5-away_team": matches[2][1][1].pk,
                "1-5-date": "2025-07-17",
            }

            # Submit step 1 to complete the wizard
            self.post(build_url.url_name, *build_url.args, data=step1_data)
            self.response_302()

            # If we have successfully moved through the wizard and been
            # redirected, the following matches would have been created.
            self.assertCountEqual(
                Match.objects.values_list(
                    "home_team__title", "away_team__title", "date", "round"
                ).order_by("round", "date"),
                [
                    (
                        matches[0][0][0].title,
                        matches[0][0][1].title,
                        date(2025, 7, 15),
                        1,
                    ),
                    (
                        matches[0][1][0].title,
                        matches[0][1][1].title,
                        date(2025, 7, 15),
                        1,
                    ),
                    (
                        matches[1][0][0].title,
                        matches[1][0][1].title,
                        date(2025, 7, 16),
                        2,
                    ),
                    (
                        matches[1][1][0].title,
                        matches[1][1][1].title,
                        date(2025, 7, 16),
                        2,
                    ),
                    (
                        matches[2][0][0].title,
                        matches[2][0][1].title,
                        date(2025, 7, 17),
                        3,
                    ),
                    (
                        matches[2][1][0].title,
                        matches[2][1][1].title,
                        date(2025, 7, 17),
                        3,
                    ),
                ],
            )

    def test_edit_match_without_external_identifier_youtube_api(self):
        """
        Test that editing a match with live streaming enabled but without
        external_identifier doesn't cause TypeError when YouTube API bind() is called.

        This test covers the original bug scenario where:
        - A match has live_stream=True
        - But obj.external_identifier is None
        - The pre_save_callback tried to bind the stream without checking identifiers
        - This caused TypeError: Missing required parameter "id"
        """
        # Create a stage with live streaming enabled but no YouTube credentials
        # This simulates the guard clause scenario
        stage = factories.StageFactory.create(
            division__season__live_stream=True,
            division__season__live_stream_client_id=None,
            division__season__live_stream_client_secret=None,
        )

        # Create a ground - doesn't need external_identifier for this test
        ground = factories.GroundFactory.create(venue__season=stage.division.season)

        # Create a match that has live streaming enabled but no external identifier
        # This is the problematic state that caused the original bug
        match = factories.MatchFactory.create(
            stage=stage,
            play_at=ground,
            live_stream=True,
            external_identifier=None,  # This is the key - no external ID
        )

        # Test editing the match - this should not raise TypeError
        edit_match_url = match.url_names["edit"]
        with self.login(self.superuser):
            # Turn off live streaming to resolve the problematic state
            data = {
                "home_team": match.home_team.pk,
                "away_team": match.away_team.pk,
                "label": match.label or "Test Match",
                "round": match.round or 1,
                "date": match.date.strftime("%Y-%m-%d"),
                "time": match.time.strftime("%H:%M"),
                "play_at": ground.pk,
                "include_in_ladder": "1" if match.include_in_ladder else "0",
                "live_stream": "0",  # Turn OFF live streaming
                "live_stream_thumbnail_image-clear": "0",
            }

            # This should complete successfully without TypeError
            data["live_stream_thumbnail_image"] = ""
            self.post(edit_match_url.url_name, *edit_match_url.args, data=data)
            self.response_302()  # Should redirect successfully

            # Verify the match was updated
            match.refresh_from_db()
            self.assertFalse(match.live_stream)
            self.assertIsNone(match.external_identifier)

    def test_json_division_builder_post_invalid_json(self):
        """Test that invalid JSON shows validation errors."""
        season = factories.SeasonFactory.create()

        invalid_json = '{"invalid": json syntax}'

        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "10",
            "form-0-json_data": invalid_json,
        }

        self.post(
            "admin:fixja:competition:season:json-builder",
            season.competition.pk,
            season.pk,
            data=data,
        )
        self.response_200()  # Should stay on form with errors

        # Check that no divisions were created
        self.assertEqual(season.divisions.count(), 0)

        # Check for validation error
        formset = self.get_context("formset")
        self.assertIsNotNone(formset)
        self.assertFalse(formset.is_valid())

    def test_json_division_builder_post_empty_json(self):
        """Test that empty JSON shows validation errors instead of success."""
        season = factories.SeasonFactory.create()

        # Empty form submission
        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "10",
            "form-0-json_data": "",  # Empty data
        }

        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:json-builder",
                season.competition.pk,
                season.pk,
                data=data,
            )
            self.response_200()  # Should stay on form with errors

        # Check that no divisions were created
        self.assertEqual(season.divisions.count(), 0)

        # Check for validation error
        formset = self.get_context("formset")
        self.assertIsNotNone(formset)
        self.assertFalse(formset.is_valid())

        # Check for specific required field error
        form = formset.forms[0]
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors, {"json_data": ["This field is required."]})

    def test_json_division_builder_post_valid_json(self):
        """Test that valid JSON creates divisions successfully."""

        season = factories.SeasonFactory.create()

        # Create a valid DivisionStructure and convert to JSON
        structure = DivisionStructure(
            title="Test Division",
            teams=["Team A", "Team B", "Team C", "Team D"],
            draw_formats={
                "round-robin-4": round_robin_format(4)
            },
            stages=[StageFixture(title="Round Robin", draw_format_ref="round-robin-4")],
        )
        valid_json = structure.model_dump_json()

        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "10",
            "form-0-json_data": valid_json,
        }

        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:json-builder",
                season.competition.pk,
                season.pk,
                data=data,
            )
            self.response_302()  # Should redirect after successful save

        # Check that division was created, with a match for every line of the format
        self.assertEqual(season.divisions.count(), 1)
        division = season.divisions.first()
        self.assertEqual(division.title, "Test Division")
        self.assertEqual(division.matches.count(), 6)

    def test_json_division_builder_duplicate_existing_division_name(self):
        """Test that existing division names cause validation errors."""

        season = factories.SeasonFactory.create()
        # Create an existing division
        existing_division = factories.DivisionFactory.create(
            season=season, title="Existing Division"
        )

        # Try to create a division with the same name
        structure = DivisionStructure(
            title="Existing Division",  # Same name as existing division
            teams=["Team A", "Team B", "Team C", "Team D"],
            draw_formats={
                "round-robin-4": round_robin_format(4)
            },
            stages=[StageFixture(title="Round Robin", draw_format_ref="round-robin-4")],
        )
        conflicting_json = structure.model_dump_json()

        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "10",
            "form-0-json_data": conflicting_json,
        }

        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:json-builder",
                season.competition.pk,
                season.pk,
                data=data,
            )
            self.response_200()  # Should stay on form with errors

        # Check that no new divisions were created
        self.assertEqual(season.divisions.count(), 1)  # Still just the existing one
        self.assertEqual(season.divisions.first(), existing_division)

        # Check for validation error
        formset = self.get_context("formset")
        self.assertIsNotNone(formset)
        self.assertFalse(formset.is_valid())

        # Check for specific duplicate name error
        form = formset.forms[0]
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {"json_data": ["A division of that name already exists in this season."]},
        )

    def test_json_division_builder_duplicate_names_within_forms(self):
        """Test that duplicate division names within the same formset cause validation errors."""

        season = factories.SeasonFactory.create()

        # Create two divisions with the same name
        structure1 = DivisionStructure(
            title="Duplicate Name",
            teams=["Team A", "Team B", "Team C", "Team D"],
            draw_formats={
                "round-robin-4": round_robin_format(4)
            },
            stages=[StageFixture(title="Round Robin", draw_format_ref="round-robin-4")],
        )
        structure2 = DivisionStructure(
            title="Duplicate Name",  # Same name as first structure
            teams=["Team E", "Team F", "Team G", "Team H"],
            draw_formats={
                "round-robin-4": round_robin_format(4)
            },
            stages=[StageFixture(title="Round Robin", draw_format_ref="round-robin-4")],
        )

        json1 = structure1.model_dump_json()
        json2 = structure2.model_dump_json()

        data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "10",
            "form-0-json_data": json1,
            "form-1-json_data": json2,
        }

        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:json-builder",
                season.competition.pk,
                season.pk,
                data=data,
            )
            self.response_200()  # Should stay on form with errors

        # Check that no divisions were created
        self.assertEqual(season.divisions.count(), 0)

        # Check for validation error
        formset = self.get_context("formset")
        self.assertIsNotNone(formset)
        self.assertFalse(formset.is_valid())

        # Check that both forms have duplicate name errors
        for i in [0, 1]:
            form = formset.forms[i]
            self.assertFalse(form.is_valid())
            self.assertEqual(
                form.errors, {"json_data": ["Division names must be unique."]}
            )

    def test_edit_match_youtube_api_basic_guard_clause(self):
        """
        Test that the YouTube API guard clauses work correctly.

        This test covers scenarios where YouTube credentials may or may not
        be configured, focusing on the original bug case where matches with
        live_stream=True but no external_identifier could cause TypeErrors.
        """
        # Test Case 1: No credentials configured (guard clause should prevent API calls)
        stage_no_creds = factories.StageFactory.create(
            division__season__live_stream=True,
            division__season__live_stream_client_id=None,
            division__season__live_stream_client_secret=None,
        )

        ground = factories.GroundFactory.create(
            venue__season=stage_no_creds.division.season
        )

        # Create match with problematic state: live_stream=True, external_identifier=None
        match = factories.MatchFactory.create(
            stage=stage_no_creds,
            play_at=ground,
            live_stream=True,
            external_identifier=None,
        )

        # Edit the match - should not cause TypeError due to guard clause
        edit_match_url = match.url_names["edit"]
        with self.login(self.superuser):
            # Turn off live streaming
            data = {
                "home_team": match.home_team.pk,
                "away_team": match.away_team.pk,
                "label": match.label or "Test Match",
                "round": match.round or 1,
                "date": match.date.strftime("%Y-%m-%d"),
                "time": match.time.strftime("%H:%M"),
                "play_at": ground.pk,
                "include_in_ladder": "1" if match.include_in_ladder else "0",
                "live_stream": "0",
                "live_stream_thumbnail_image-clear": "0",
            }

            # This should complete successfully without TypeError
            data["live_stream_thumbnail_image"] = ""
            self.post(edit_match_url.url_name, *edit_match_url.args, data=data)
            self.response_302()  # Should redirect successfully

            # Verify the match was updated
            match.refresh_from_db()
            self.assertFalse(match.live_stream)
            self.assertIsNone(match.external_identifier)

    def test_undo_draw_with_dependent_matches(self):
        """Test that undo_draw handles matches with eval_related dependencies correctly."""
        # Create a stage with two rounds as described in the issue
        stage = factories.StageFactory.create()

        # Round 1: Create match with teams assigned by factory
        match1 = factories.MatchFactory.create(stage=stage, round=1, label="Match 1")

        # Round 2: Create matches that depend on Round 1 results
        # These matches will have eval_related fields pointing to match1
        _match2 = factories.MatchFactory.create(
            stage=stage,
            round=2,
            label="Winner vs Loser",
            home_team=None,  # Don't create teams, rely on eval fields
            away_team=None,
            home_team_eval="W",  # Home team is winner of match1
            home_team_eval_related=match1,
            away_team_eval="L",  # Away team is loser of match1
            away_team_eval_related=match1,
        )

        # Verify that the dependent match shows the correct team titles
        expected_matches = [
            (
                match1.home_team.title,
                match1.away_team.title,
            ),  # match1 has teams assigned by factory
            ("Winner Match 1", "Loser Match 1"),  # match2 references match1
        ]
        actual_matches = [
            (m.home_team_title, m.away_team_title)
            for m in stage.matches.order_by("round", "pk")._team_titles()
        ]
        self.assertCountEqual(actual_matches, expected_matches)

        # Now test the undo_draw view - this should work without ProtectedError
        undo_draw_url = stage.url_names["undo"]

        self.post(undo_draw_url.url_name, *undo_draw_url.args)
        self.response_302()  # Should redirect successfully without error

        # Verify all matches from the stage were deleted
        self.assertCountEqual(stage.matches.all(), [])

    def test_undo_draw_with_complex_interleaved_dependencies(self):
        """
        Test that undo_draw handles complex interleaved match dependencies correctly.

        This test creates a tournament bracket-like structure with multiple rounds
        where matches depend on results from previous rounds in a complex way:
        - Round 1: Two base matches
        - Round 2: Two matches depending on Round 1 results (winners vs winners, losers vs losers)
        - Round 3: Two matches depending on Round 2 results with cross-dependencies

        This tests that the ordering of deletion doesn't matter and that all
        dependent matches are properly handled regardless of their creation order
        or interdependencies.
        """
        stage = factories.StageFactory.create()

        # Round 1: Create two base matches
        match1 = factories.MatchFactory.create(stage=stage, round=1, label="Match 1")
        match2 = factories.MatchFactory.create(stage=stage, round=1, label="Match 2")

        # Round 2: Create matches that depend on Round 1 results
        # Set home_team=None, away_team=None to rely on eval fields
        match3 = factories.MatchFactory.create(
            stage=stage,
            round=2,
            label="Winners Semi",
            home_team=None,
            away_team=None,
            home_team_eval="W",  # Winner of match1
            home_team_eval_related=match1,
            away_team_eval="W",  # Winner of match2
            away_team_eval_related=match2,
        )
        match4 = factories.MatchFactory.create(
            stage=stage,
            round=2,
            label="Losers Semi",
            home_team=None,
            away_team=None,
            home_team_eval="L",  # Loser of match1
            home_team_eval_related=match1,
            away_team_eval="L",  # Loser of match2
            away_team_eval_related=match2,
        )

        # Round 3: Create matches with cross-dependencies on Round 2
        _match5 = factories.MatchFactory.create(
            stage=stage,
            round=3,
            label="Final",
            home_team=None,
            away_team=None,
            home_team_eval="W",  # Winner of match3
            home_team_eval_related=match3,
            away_team_eval="L",  # Loser of match4 (cross-dependency)
            away_team_eval_related=match4,
        )
        _match6 = factories.MatchFactory.create(
            stage=stage,
            round=3,
            label="3rd Place",
            home_team=None,
            away_team=None,
            home_team_eval="L",  # Loser of match3
            home_team_eval_related=match3,
            away_team_eval="W",  # Winner of match4 (cross-dependency)
            away_team_eval_related=match4,
        )

        # Verify the complex dependency structure is set up correctly
        expected_teams = [
            # match1 and match2 have actual teams (from factory)
            (match1.home_team.title, match1.away_team.title),
            (match2.home_team.title, match2.away_team.title),
            # matches 3-6 have eval-based team titles
            ("Winner Match 1", "Winner Match 2"),  # match3
            ("Loser Match 1", "Loser Match 2"),  # match4
            ("Winner Winners Semi", "Loser Losers Semi"),  # match5
            ("Loser Winners Semi", "Winner Losers Semi"),  # match6
        ]
        actual_teams = [
            (m.home_team_title, m.away_team_title)
            for m in stage.matches.all()._team_titles().order_by("round", "pk")
        ]
        self.assertCountEqual(actual_teams, expected_teams)

        # Now test the undo_draw view with this complex dependency structure
        # This should work without ProtectedError despite the interleaved dependencies
        undo_draw_url = stage.url_names["undo"]

        self.post(undo_draw_url.url_name, *undo_draw_url.args)
        self.response_302()  # Should redirect successfully without error

        # Verify all matches from the stage were deleted despite complex dependencies
        self.assertCountEqual(stage.matches.all(), [])

    def test_division_export_json(self):
        """Test that division JSON export works correctly."""
        # Create a simple division with teams and a stage
        division = factories.DivisionFactory.create(title="Test Division")

        # Create some teams
        team1 = factories.TeamFactory.create(division=division, title="Team A")
        team2 = factories.TeamFactory.create(division=division, title="Team B")

        # Create a stage with a simple match
        stage = factories.StageFactory.create(division=division, title="Round Robin")
        factories.MatchFactory.create(
            stage=stage,
            home_team=team1,
            away_team=team2,
            round=1,
        )

        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:season:division:export-json",
                division.season.competition.pk,
                division.season.pk,
                division.pk,
            )
        self.response_200()

        # Check response content type and headers
        self.assertResponseHeaders(
            {
                "Content-Type": "application/json",
                "Content-Disposition": f'attachment; filename="{division.season.competition.slug}_{division.season.slug}_{division.slug}.json"',
            }
        )

        structure = DivisionStructure.model_validate_json(
            self.last_response.content.decode()
        )

        # Verify basic structure
        self.assertEqual(structure.title, "Test Division")
        self.assertEqual(structure.teams, ["Team A", "Team B"])
        self.assertEqual([s.title for s in structure.stages], ["Round Robin"])

    @patch("googleapiclient.discovery.build")
    def test_bug_203_add_match_with_live_streaming_enabled(self, mock_discovery_build):
        """
        Test that creating a match through admin UI does not raise NoReverseMatch
        when live streaming is enabled with YouTube credentials configured.

        Refs: https://github.com/goodtune/vitriolic/issues/203
        """
        stage = factories.StageFactory.create(
            division__season__live_stream=True,
            division__season__live_stream_project_id="test-project-123",
            division__season__live_stream_client_id="test-client-id",
            division__season__live_stream_client_secret="test-client-secret",
        )
        team1 = factories.TeamFactory.create(division=stage.division)
        team2 = factories.TeamFactory.create(division=stage.division)
        ground = factories.GroundFactory.create()

        data = {
            "home_team": team1.pk,
            "away_team": team2.pk,
            "label": "Test Match",
            "round": 1,
            "date": "2025-05-01",
            "time": "14:00:00",
            "play_at": ground.pk,
            "include_in_ladder": "1",
            "live_stream": "0",
            "live_stream_thumbnail_image-clear": "0",
        }

        add_match = Match(stage=stage).url_names["add"]
        data["live_stream_thumbnail_image"] = ""
        self.post(add_match.url_name, *add_match.args, data=data)
        self.response_302()

    @patch("tournamentcontrol.competition.tasks.set_youtube_thumbnail")
    @patch(
        "tournamentcontrol.competition.models.Season.youtube", new_callable=PropertyMock
    )
    def test_resync_live_stream_sends_unescaped_apostrophes(
        self, mock_youtube_prop, mock_thumbnail
    ):
        """Resync must push raw apostrophes to YouTube, not ``&#x27;``.

        Refs: apostrophe regression introduced in PR #206.
        """
        stage = factories.StageFactory.create(
            division__title="Men's Open",
            division__season__live_stream=True,
            division__season__live_stream_project_id="test-project-123",
            division__season__live_stream_client_id="test-client-id",
            division__season__live_stream_client_secret="test-client-secret",
        )
        ground = factories.GroundFactory.create(
            venue__season=stage.division.season,
            external_identifier="yt-stream-abc",
        )
        home = factories.TeamFactory.create(
            title="St George's", division=stage.division
        )
        away = factories.TeamFactory.create(title="O'Connor", division=stage.division)
        match = factories.MatchFactory.create(
            stage=stage,
            play_at=ground,
            home_team=home,
            away_team=away,
            label="Semi's",
            live_stream=True,
            external_identifier="yt-broadcast-xyz",
            date=date(2025, 5, 1),
            time=time(14, 0),
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
        )

        mock_youtube = MagicMock()
        mock_youtube_prop.return_value = mock_youtube
        mock_youtube.liveBroadcasts.return_value.update.return_value.execute.return_value = {
            "id": match.external_identifier,
        }
        mock_youtube.liveBroadcasts.return_value.bind.return_value.execute.return_value = {
            "contentDetails": {"boundStreamId": ground.external_identifier},
        }

        resync = match.url_names["resync-live-stream"]
        with self.login(self.superuser):
            self.post(resync.url_name, *resync.args)
        self.response_302()

        update_call = mock_youtube.liveBroadcasts.return_value.update.call_args
        body = update_call.kwargs["body"]
        title = body["snippet"]["title"]
        description = body["snippet"]["description"]

        self.assertEqual(body["id"], "yt-broadcast-xyz")
        self.assertIn("Men's Open", title)
        self.assertIn("St George's", title)
        self.assertIn("O'Connor", title)
        self.assertNotIn("&#x27;", title)
        self.assertNotIn("&#39;", title)
        self.assertNotIn("&#x27;", description)
        self.assertNotIn("&#39;", description)

    @patch(
        "tournamentcontrol.competition.models.Season.youtube", new_callable=PropertyMock
    )
    def test_resync_live_stream_refuses_when_not_streaming(self, mock_youtube_prop):
        """Resync refuses and flashes an error when the match has no broadcast."""
        stage = factories.StageFactory.create(
            division__season__live_stream=True,
            division__season__live_stream_project_id="test-project-123",
            division__season__live_stream_client_id="test-client-id",
            division__season__live_stream_client_secret="test-client-secret",
        )
        ground = factories.GroundFactory.create(venue__season=stage.division.season)
        match = factories.MatchFactory.create(
            stage=stage,
            play_at=ground,
            live_stream=False,
            external_identifier=None,
            date=date(2025, 5, 1),
            time=time(14, 0),
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
        )

        mock_youtube = MagicMock()
        mock_youtube_prop.return_value = mock_youtube

        resync = match.url_names["resync-live-stream"]
        with self.login(self.superuser):
            self.post(resync.url_name, *resync.args)
        self.response_302()

        mock_youtube.liveBroadcasts.return_value.update.assert_not_called()

    def test_match_live_stream_lists_only_camera_equipped_matches_for_the_day(self):
        stage = factories.StageFactory.create()
        camera_ground = factories.GroundFactory.create(
            venue__season=stage.division.season, live_stream=True
        )
        plain_ground = factories.GroundFactory.create(
            venue__season=stage.division.season, live_stream=False
        )
        on_camera = factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            date=date(2025, 5, 1),
            time=time(14, 0),
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
        )
        factories.MatchFactory.create(
            stage=stage,
            play_at=plain_ground,
            date=date(2025, 5, 1),
            time=time(15, 0),
            datetime=datetime(2025, 5, 1, 5, 0, tzinfo=ZoneInfo("UTC")),
        )
        factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            date=date(2025, 5, 2),
            time=time(14, 0),
            datetime=datetime(2025, 5, 2, 4, 0, tzinfo=ZoneInfo("UTC")),
        )
        season = stage.division.season

        with self.login(self.superuser):
            self.get(
                "admin:fixja:match-live-stream",
                season.competition.pk,
                season.pk,
                "20250501",
            )
        self.response_200()

        formset = self.last_response.context["formset"]
        listed_pks = {form.instance.pk for form in formset.forms}
        self.assertEqual(listed_pks, {on_camera.pk})

    def test_match_live_stream_post_toggles_only_selected_matches(self):
        stage = factories.StageFactory.create()
        camera_ground = factories.GroundFactory.create(
            venue__season=stage.division.season, live_stream=True
        )
        match_to_turn_on = factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            live_stream=False,
            date=date(2025, 5, 1),
            time=time(14, 0),
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
        )
        match_to_turn_off = factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            live_stream=True,
            date=date(2025, 5, 1),
            time=time(15, 0),
            datetime=datetime(2025, 5, 1, 5, 0, tzinfo=ZoneInfo("UTC")),
        )
        season = stage.division.season

        data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "2",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": str(match_to_turn_on.pk),
            "form-0-live_stream": "1",
            "form-1-id": str(match_to_turn_off.pk),
            "form-1-live_stream": "0",
        }

        with self.login(self.superuser):
            self.post(
                "admin:fixja:match-live-stream",
                season.competition.pk,
                season.pk,
                "20250501",
                data=data,
            )
        self.response_302()

        match_to_turn_on.refresh_from_db()
        match_to_turn_off.refresh_from_db()
        self.assertTrue(match_to_turn_on.live_stream)
        self.assertFalse(match_to_turn_off.live_stream)

    def test_runsheet_and_season_schedule_link_to_bulk_live_stream_view(self):
        stage = factories.StageFactory.create()
        camera_ground = factories.GroundFactory.create(
            venue__season=stage.division.season, live_stream=True
        )
        factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            date=date(2025, 5, 1),
            time=time(14, 0),
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
        )
        season = stage.division.season

        expected_url = reverse(
            "admin:fixja:match-live-stream",
            args=[season.competition.pk, season.pk, "20250501"],
        )

        with self.login(self.superuser):
            self.get(
                "admin:fixja:match-runsheet",
                season.competition.pk,
                season.pk,
                "20250501",
            )
            self.response_200()
            self.assertContains(self.last_response, expected_url)

            season_edit_response = self.client.get(str(season.urls["edit"]))
            self.assertContains(season_edit_response, expected_url)

    def test_runsheet_shows_resync_icon_only_when_broadcast_exists(self):
        stage = factories.StageFactory.create()
        camera_ground = factories.GroundFactory.create(
            venue__season=stage.division.season, live_stream=True
        )
        streaming_match = factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            live_stream=True,
            live_stream_bind="yt-bound-abc",
            external_identifier="yt-broadcast-abc",
            date=date(2025, 5, 1),
            time=time(14, 0),
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
        )
        not_yet_streaming = factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            live_stream=False,
            external_identifier=None,
            date=date(2025, 5, 1),
            time=time(15, 0),
            datetime=datetime(2025, 5, 1, 5, 0, tzinfo=ZoneInfo("UTC")),
        )
        season = stage.division.season

        streaming_resync_url = reverse(
            "admin:fixja:competition:season:division:stage:match:resync-live-stream",
            args=[
                season.competition.pk,
                season.pk,
                stage.division.pk,
                stage.pk,
                streaming_match.pk,
            ],
        )
        not_yet_streaming_resync_url = reverse(
            "admin:fixja:competition:season:division:stage:match:resync-live-stream",
            args=[
                season.competition.pk,
                season.pk,
                stage.division.pk,
                stage.pk,
                not_yet_streaming.pk,
            ],
        )

        with self.login(self.superuser):
            self.get(
                "admin:fixja:match-runsheet",
                season.competition.pk,
                season.pk,
                "20250501",
            )
        self.response_200()
        self.assertContains(self.last_response, streaming_resync_url)
        self.assertNotContains(self.last_response, not_yet_streaming_resync_url)

    @patch("tournamentcontrol.competition.admin.sync_live_stream")
    def test_match_live_stream_post_enqueues_sync_when_configured(
        self, mock_sync_live_stream
    ):
        stage = factories.StageFactory.create(
            division__season__live_stream=True,
            division__season__live_stream_client_id="test-client-id",
            division__season__live_stream_client_secret="test-client-secret",
        )
        camera_ground = factories.GroundFactory.create(
            venue__season=stage.division.season, live_stream=True
        )
        match_to_turn_on = factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            live_stream=False,
            external_identifier=None,
            date=date(2025, 5, 1),
            time=time(14, 0),
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
        )
        season = stage.division.season

        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": str(match_to_turn_on.pk),
            "form-0-live_stream": "1",
        }

        with self.login(self.superuser):
            self.post(
                "admin:fixja:match-live-stream",
                season.competition.pk,
                season.pk,
                "20250501",
                data=data,
            )
        self.response_302()

        mock_sync_live_stream.s.assert_called_once_with(
            match_to_turn_on.pk, base_url=ANY
        )
        mock_sync_live_stream.s.return_value.apply_async.assert_called_once()

    @patch("tournamentcontrol.competition.admin.sync_live_stream")
    def test_match_live_stream_post_skips_sync_when_season_not_configured(
        self, mock_sync_live_stream
    ):
        stage = factories.StageFactory.create()
        camera_ground = factories.GroundFactory.create(
            venue__season=stage.division.season, live_stream=True
        )
        match_to_turn_on = factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            live_stream=False,
            date=date(2025, 5, 1),
            time=time(14, 0),
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
        )
        season = stage.division.season

        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": str(match_to_turn_on.pk),
            "form-0-live_stream": "1",
        }

        with self.login(self.superuser):
            self.post(
                "admin:fixja:match-live-stream",
                season.competition.pk,
                season.pk,
                "20250501",
                data=data,
            )
        self.response_302()

        mock_sync_live_stream.s.assert_not_called()

    @patch("tournamentcontrol.competition.admin.sync_live_stream")
    def test_match_live_stream_resync_queues_all_streaming_matches(
        self, mock_sync_live_stream
    ):
        stage = factories.StageFactory.create(
            division__season__live_stream=True,
            division__season__live_stream_client_id="test-client-id",
            division__season__live_stream_client_secret="test-client-secret",
        )
        camera_ground = factories.GroundFactory.create(
            venue__season=stage.division.season, live_stream=True
        )
        streaming_match_1 = factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            live_stream=True,
            external_identifier="yt-broadcast-1",
            date=date(2025, 5, 1),
            time=time(14, 0),
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
        )
        streaming_match_2 = factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            live_stream=True,
            external_identifier="yt-broadcast-2",
            date=date(2025, 5, 1),
            time=time(15, 0),
            datetime=datetime(2025, 5, 1, 5, 0, tzinfo=ZoneInfo("UTC")),
        )
        # Marked live_stream but never actually broadcast (e.g. toggled via the
        # bulk view before sync_live_stream was wired up to it) -- this is the
        # create half of create-or-update, so it must still be queued.
        never_broadcast = factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            live_stream=True,
            external_identifier=None,
            date=date(2025, 5, 1),
            time=time(16, 0),
            datetime=datetime(2025, 5, 1, 6, 0, tzinfo=ZoneInfo("UTC")),
        )
        # Not streaming -- must be skipped.
        factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            live_stream=False,
            external_identifier=None,
            date=date(2025, 5, 1),
            time=time(17, 0),
            datetime=datetime(2025, 5, 1, 7, 0, tzinfo=ZoneInfo("UTC")),
        )
        # Marked live_stream, never broadcast, AND no scheduled datetime --
        # there's nothing to insert yet, so this must still be skipped. A
        # distinct round keeps get_datetime() from borrowing a sibling
        # match's datetime in the same stage/round.
        factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            live_stream=True,
            external_identifier=None,
            date=date(2025, 5, 1),
            time=None,
            datetime=None,
            round=99,
        )
        season = stage.division.season

        with self.login(self.superuser):
            self.post(
                "admin:fixja:match-live-stream-resync",
                season.competition.pk,
                season.pk,
                "20250501",
            )
        self.response_302()

        queued_pks = {call.args[0] for call in mock_sync_live_stream.s.call_args_list}
        self.assertEqual(
            queued_pks,
            {streaming_match_1.pk, streaming_match_2.pk, never_broadcast.pk},
        )
        self.assertEqual(mock_sync_live_stream.s.return_value.apply_async.call_count, 3)

    @patch("tournamentcontrol.competition.admin.sync_live_stream")
    def test_match_live_stream_resync_refuses_when_not_configured(
        self, mock_sync_live_stream
    ):
        stage = factories.StageFactory.create()
        season = stage.division.season

        with self.login(self.superuser):
            self.post(
                "admin:fixja:match-live-stream-resync",
                season.competition.pk,
                season.pk,
                "20250501",
            )
        self.response_302()

        mock_sync_live_stream.s.assert_not_called()

    @patch("tournamentcontrol.competition.admin.sync_live_stream")
    def test_match_live_stream_resync_ignores_get(self, mock_sync_live_stream):
        stage = factories.StageFactory.create(
            division__season__live_stream=True,
            division__season__live_stream_client_id="test-client-id",
            division__season__live_stream_client_secret="test-client-secret",
        )
        camera_ground = factories.GroundFactory.create(
            venue__season=stage.division.season, live_stream=True
        )
        factories.MatchFactory.create(
            stage=stage,
            play_at=camera_ground,
            live_stream=True,
            external_identifier="yt-broadcast-1",
            date=date(2025, 5, 1),
            time=time(14, 0),
            datetime=datetime(2025, 5, 1, 4, 0, tzinfo=ZoneInfo("UTC")),
        )
        season = stage.division.season

        with self.login(self.superuser):
            self.get(
                "admin:fixja:match-live-stream-resync",
                season.competition.pk,
                season.pk,
                "20250501",
            )
        self.response_302()

        mock_sync_live_stream.s.assert_not_called()


class TeamEditViewQueryTests(TestCase):
    """
    The team edit page in the competition admin renders the team's
    ``people`` (``TeamAssociation``) list using the ``admin_list``
    template tag. Without prefetching, that produces one
    ``competition_person`` query and one ``competition_teamrole`` query
    per association. Pin the view's query count so the same upper bound
    holds whether the team is empty or fully squadded - any per-player
    scaling trips the large case.
    """

    @classmethod
    def setUpTestData(cls):
        cls.empty_team = factories.TeamFactory.create()
        cls.full_team = factories.TeamFactory.create()
        for _ in range(20):
            factories.TeamAssociationFactory.create(
                team=cls.full_team,
                person=factories.PersonFactory.create(club=cls.full_team.club),
            )

    def test_empty_team_query_count(self):
        edit_team = self.empty_team.url_names["edit"]
        with self.login(self.superuser):
            self.assertGoodView(
                edit_team.url_name,
                *edit_team.args,
                # The tree in the rail opens the folders down to the team
                # (28 in Workbook, 30 in Explorer).
                test_query_count=30,
            )

    def test_full_team_query_count(self):
        edit_team = self.full_team.url_names["edit"]
        with self.login(self.superuser):
            self.assertGoodView(
                edit_team.url_name,
                *edit_team.args,
                # The tree in the rail opens the folders down to the team
                # (28 in Workbook, 30 in Explorer).
                test_query_count=30,
            )


class EditViewPermissionTests(TestCase):
    """
    Editing an existing record must be governed by the ``change_<model>``
    permission (including object-level permissions assigned through the
    permissions tab), while creating a record is governed by ``add_<model>``.
    """

    @classmethod
    def setUpTestData(cls):
        cls.season = factories.SeasonFactory.create()
        cls.other = factories.SeasonFactory.create()
        cls.staff = factories.UserFactory.create(is_staff=True)

    def test_object_level_change_permission_allows_edit(self):
        assign_perm("competition.change_season", self.staff, self.season)
        with self.login(self.staff):
            self.get(
                "admin:fixja:competition:season:edit", *self.season._get_url_args()
            )
            self.response_200()
            css = by_shell(workbook='class="wb-input" ', explorer="")
            self.assertResponseContains(
                f'<input type="text" name="title" value="{self.season.title}" '
                f'maxlength="255" {css}required id="id_title">'
            )

    def test_object_level_change_permission_is_scoped_to_object(self):
        assign_perm("competition.change_season", self.staff, self.season)
        with self.login(self.staff):
            self.get("admin:fixja:competition:season:edit", *self.other._get_url_args())
            self.response_403()

    def test_change_permission_does_not_allow_add(self):
        assign_perm("competition.change_season", self.staff)
        with self.login(self.staff):
            self.get("admin:fixja:competition:season:add", self.season.competition_id)
            self.response_403()

    def test_add_permission_allows_add_but_not_edit(self):
        assign_perm("competition.add_season", self.staff)
        with self.login(self.staff):
            self.get("admin:fixja:competition:season:add", self.season.competition_id)
            self.response_200()
            self.get(
                "admin:fixja:competition:season:edit", *self.season._get_url_args()
            )
            self.response_403()


class BulkCreateDivisionTests(MessagesTestMixin, TestCase):
    """Add several divisions to a season at once."""

    viewname = "admin:fixja:competition:season:division:bulk"

    def setUp(self):
        super().setUp()
        self.season = factories.SeasonFactory.create(mode=DAILY)
        self.args = (self.season.competition_id, self.season.pk)

    def rows(self, *rows, total=None):
        data = {
            "form-TOTAL_FORMS": str(len(rows) if total is None else total),
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "50",
        }
        for index, row in enumerate(rows):
            # A browser posts the "No" the draft select shows on blank rows.
            for name, value in {"draft": "0", **row}.items():
                data[f"form-{index}-{name}"] = value
        return data

    def division(self, title, **kwargs):
        return {
            "title": title,
            "short_title": "",
            "games_per_day": "3",
            "forfeit_for_score": "5",
            "forfeit_against_score": "0",
            **kwargs,
        }

    def test_season_edit_offers_bulk_create(self):
        with self.login(self.superuser):
            self.get("admin:fixja:competition:season:edit", *self.args)
            self.response_200()
            self.assertResponseContains(
                by_shell(
                    workbook=bulk_dialog(
                        self.reverse(self.viewname, *self.args),
                        "division",
                        "Add several divisions",
                    ),
                    explorer=bulk_link(
                        self.reverse(self.viewname, *self.args),
                        "division",
                        "Add several divisions",
                    ),
                )
            )

    def test_get_shows_count_blank_rows_after_existing_divisions(self):
        factories.DivisionFactory.create(season=self.season, order=4)
        self.assertLoginRequired(self.viewname, *self.args)
        with self.login(self.superuser):
            self.get(self.viewname, *self.args, data={"count": "3"})
            self.response_200()
            self.assertResponseContains(
                '<input type="hidden" name="form-TOTAL_FORMS" value="3" '
                'id="id_form-TOTAL_FORMS">'
            )
            self.assertResponseContains(
                by_shell(
                    workbook='<label for="id_form-0-games_per_day" class="field_name">'
                    "Games per day</label>",
                    explorer="<th>Games per day</th>",
                )
            )
            formset = self.get_context("formset")
            self.assertEqual([form.instance.order for form in formset], [5, 6, 7])
            self.assertEqual([form.instance.pk for form in formset], [None] * 3)

    def test_get_count_is_limited(self):
        with self.login(self.superuser):
            for count, rows in (("0", 1), ("500", 50), ("x", 5)):
                with self.subTest(count=count):
                    self.get(self.viewname, *self.args, data={"count": count})
                    self.response_200()
                    self.assertEqual(len(self.get_context("formset").forms), rows)

    def test_weekly_season_has_no_games_per_day(self):
        season = factories.SeasonFactory.create()
        with self.login(self.superuser):
            self.get(self.viewname, season.competition_id, season.pk)
            self.response_200()
            formset = self.get_context("formset")
            self.assertNotIn("games_per_day", formset.forms[0].fields)

    def test_post_creates_divisions_in_row_order(self):
        factories.DivisionFactory.create(season=self.season, title="Mixed", order=1)
        data = self.rows(
            self.division("Men's Open", short_title="Men"),
            {},
            self.division("Women's Open", draft="1", games_per_day="2"),
        )
        with self.login(self.superuser):
            self.post(self.viewname, *self.args, data=data)
            self.response_302()
            self.assertRedirects(
                self.last_response,
                self.season.urls["edit"] + "#divisions-tab",
                fetch_redirect_response=False,
            )
        self.assertEqual(
            list(
                self.season.divisions.order_by("order").values_list(
                    "title",
                    "short_title",
                    "order",
                    "draft",
                    "games_per_day",
                    "forfeit_for_score",
                    "forfeit_against_score",
                )
            ),
            [
                ("Mixed", "", 1, False, 2, 5, 0),
                ("Men's Open", "Men", 2, False, 3, 5, 0),
                ("Women's Open", "", 3, True, 2, 5, 0),
            ],
        )

    def test_post_refuses_duplicate_titles(self):
        factories.DivisionFactory.create(season=self.season, title="Mixed")
        data = self.rows(
            self.division("Men's Open"),
            self.division("Men's Open"),
            self.division("Mixed"),
        )
        with self.login(self.superuser):
            self.post(self.viewname, *self.args, data=data)
            self.response_200()
            formset = self.get_context("formset")
            self.assertEqual(
                [form.errors.get("title") for form in formset],
                [
                    None,
                    ["This title is already used in row 1."],
                    ["Division with this Title already exists."],
                ],
            )
        self.assertEqual(self.season.divisions.count(), 1)

    def test_post_refuses_no_rows(self):
        with self.login(self.superuser):
            self.post(self.viewname, *self.args, data=self.rows({}, {}))
            self.response_200()
            self.assertResponseContains(
                by_shell(
                    workbook='<div class="wb-problems" role="alert" tabindex="-1">'
                    "<h2>Please check the form</h2>"
                    "<ul><li>Fill in at least one row.</li></ul></div>",
                    explorer='<div class="form-errors" role="alert">'
                    '<svg class="icon" aria-hidden="true" focusable="false"><use href="/static/touchtechnology/admin/explorer/img/icons.svg#alert"></use></svg>'
                    "<ul><li>Fill in at least one row.</li></ul></div>",
                )
            )
        self.assertEqual(self.season.divisions.count(), 0)

    def test_post_refuses_too_many_rows(self):
        data = self.rows(*(self.division(f"D{n}") for n in range(51)))
        with self.login(self.superuser):
            self.post(self.viewname, *self.args, data=data)
            self.response_200()
        self.assertEqual(self.season.divisions.count(), 0)

    def test_permission_required(self):
        staff = UserFactory.create(is_staff=True)
        data = self.rows(self.division("Men's Open"))
        with self.login(staff):
            self.get(self.viewname, *self.args)
            self.response_403()
            self.post(self.viewname, *self.args, data=data)
            self.response_403()
        assign_perm("competition.add_division", staff)
        with self.login(staff):
            self.post(self.viewname, *self.args, data=data)
            self.response_302()
        self.assertEqual(self.season.divisions.get().title, "Men's Open")


class BulkCreateTeamTests(MessagesTestMixin, TestCase):
    """Add several teams to a division at once."""

    viewname = "admin:fixja:competition:season:division:team:bulk"

    def setUp(self):
        super().setUp()
        self.division = factories.DivisionFactory.create()
        self.competition = self.division.season.competition
        self.args = (self.competition.pk, self.division.season_id, self.division.pk)

    def rows(self, *rows):
        data = {
            "form-TOTAL_FORMS": str(len(rows)),
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "50",
        }
        for index, row in enumerate(rows):
            for name, value in row.items():
                data[f"form-{index}-{name}"] = value
        return data

    def test_division_edit_offers_bulk_create(self):
        with self.login(self.superuser):
            self.get("admin:fixja:competition:season:division:edit", *self.args)
            self.response_200()
            self.assertResponseContains(
                by_shell(
                    workbook=bulk_dialog(
                        self.reverse(self.viewname, *self.args),
                        "team",
                        "Add several teams",
                    ),
                    explorer=bulk_link(
                        self.reverse(self.viewname, *self.args),
                        "team",
                        "Add several teams",
                    ),
                )
            )

    def test_get_shows_count_blank_rows_after_existing_teams(self):
        factories.TeamFactory.create(division=self.division, order=2)
        self.assertLoginRequired(self.viewname, *self.args)
        with self.login(self.superuser):
            self.get(self.viewname, *self.args, data={"count": "4"})
            self.response_200()
            self.assertResponseContains(
                '<input type="hidden" name="form-TOTAL_FORMS" value="4" '
                'id="id_form-TOTAL_FORMS">'
            )
            formset = self.get_context("formset")
            self.assertEqual([form.instance.order for form in formset], [3, 4, 5, 6])
            self.assertEqual(
                [field.name for field in formset.forms[0].visible_fields()], ["title"]
            )

    def test_post_creates_teams_in_row_order(self):
        factories.TeamFactory.create(division=self.division, title="Alpha", order=1)
        data = self.rows({"title": "Bravo"}, {"title": ""}, {"title": "Charlie"})
        with self.login(self.superuser):
            self.post(self.viewname, *self.args, data=data)
            self.response_302()
            self.assertRedirects(
                self.last_response,
                self.division.urls["edit"] + "#teams-tab",
                fetch_redirect_response=False,
            )
        self.assertEqual(
            list(self.division.teams.order_by("order").values_list("title", "order")),
            [("Alpha", 1), ("Bravo", 2), ("Charlie", 3)],
        )

    def test_post_with_clubs_defaults_title_to_club(self):
        nzl = factories.ClubFactory.create(title="New Zealand")
        aus = factories.ClubFactory.create(title="Australia")
        other = factories.ClubFactory.create(title="Elsewhere")
        self.competition.clubs.set([nzl, aus])
        with self.login(self.superuser):
            self.get(self.viewname, *self.args)
            formset = self.get_context("formset")
            self.assertEqual(
                list(formset.forms[0].fields["club"].queryset.order_by("title")),
                [aus, nzl],
            )
            rows = [
                {"title": "", "club": str(nzl.pk)},
                {"title": "Kangaroos", "club": str(aus.pk)},
            ]
            self.post(
                self.viewname,
                *self.args,
                data=self.rows(*rows, {"title": "", "club": str(other.pk)}),
            )
            self.response_200()
            self.assertEqual(
                [list(form.errors) for form in self.get_context("formset")],
                [[], [], ["club", "title"]],
            )
            self.post(self.viewname, *self.args, data=self.rows(*rows))
            self.response_302()
        self.assertEqual(
            list(self.division.teams.order_by("order").values_list("title", "club")),
            [("New Zealand", nzl.pk), ("Kangaroos", aus.pk)],
        )

    def test_post_refuses_duplicate_titles(self):
        factories.TeamFactory.create(division=self.division, title="Alpha")
        data = self.rows({"title": "Bravo"}, {"title": "Bravo"}, {"title": "Alpha"})
        with self.login(self.superuser):
            self.post(self.viewname, *self.args, data=data)
            self.response_200()
            self.assertEqual(
                [form.errors.get("title") for form in self.get_context("formset")],
                [
                    None,
                    ["This title is already used in row 1."],
                    ["Team with this Title already exists."],
                ],
            )
        self.assertEqual(self.division.teams.count(), 1)

    def test_permission_required(self):
        staff = UserFactory.create(is_staff=True)
        data = self.rows({"title": "Bravo"})
        with self.login(staff):
            self.get(self.viewname, *self.args)
            self.response_403()
            self.post(self.viewname, *self.args, data=data)
            self.response_403()
        assign_perm("competition.add_team", staff)
        with self.login(staff):
            self.post(self.viewname, *self.args, data=data)
            self.response_302()
        self.assertEqual(self.division.teams.get().title, "Bravo")


class SeasonEditForfeitNotificationsTests(TestCase):
    """
    The season page lists every user on the site in its "forfeit
    notifications" box, which made one of the most visited pages of the
    event admin slow to load. The box is left off the page; the people
    already chosen keep being notified.
    """

    @classmethod
    def setUpTestData(cls):
        cls.season = factories.SeasonFactory.create(timezone="Australia/Sydney")
        cls.recipients = factories.UserFactory.create_batch(3)
        cls.season.forfeit_notifications.set(cls.recipients)

    def test_season_page_has_no_forfeit_notifications(self):
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:season:edit", *self.season._get_url_args()
            )
            self.response_200()
            self.assertNotIn("forfeit_notifications", self.get_context("form").fields)

    def test_saving_the_season_keeps_its_forfeit_notifications(self):
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:edit",
                *self.season._get_url_args(),
                data={
                    "title": "Renamed",
                    "slug": self.season.slug,
                    "mode": self.season.mode,
                    "timezone": "Australia/Sydney",
                    "live_stream_privacy": "public",
                },
            )
            self.response_302()
        self.season.refresh_from_db()
        self.assertEqual(self.season.title, "Renamed")
        self.assertCountEqual(self.season.forfeit_notifications.all(), self.recipients)


class MatchResultsQueryTests(TestCase):
    """
    Results are entered on one page per day of matches. Each match drew its
    two teams, its ground, its division and the forfeit winner choices with
    queries of their own, so a full day of an event took hundreds of
    queries. The same query budget now holds however many matches the day
    has.
    """

    kickoff = datetime(2026, 10, 8, 9, 0, tzinfo=ZoneInfo("UTC"))

    def setUp(self):
        super().setUp()
        self.season = factories.SeasonFactory.create(timezone="UTC")
        venue = factories.VenueFactory.create(season=self.season)
        self.ground = factories.GroundFactory.create(venue=venue)
        self.few = self._day(date(2026, 10, 8), 2)
        self.many = self._day(date(2026, 10, 9), 10)

    def _day(self, day, matches):
        stage = factories.StageFactory.create(division__season=self.season)
        created = []
        for number in range(matches):
            when = datetime.combine(day, time(9 + number), tzinfo=ZoneInfo("UTC"))
            created.append(
                factories.MatchFactory.create(
                    stage=stage,
                    home_team=factories.TeamFactory.create(division=stage.division),
                    away_team=factories.TeamFactory.create(division=stage.division),
                    play_at=self.ground,
                    datetime=when,
                    date=when.date(),
                    time=when.time(),
                )
            )
        return created

    def get_day(self, matches, **kwargs):
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:match-results",
                self.season.competition.pk,
                self.season.pk,
                matches[0].date.strftime("%Y%m%d"),
                **kwargs,
            )

    # The tree in the rail opens the season's match days down to this one.
    def test_few_matches_query_count(self):
        self.get_day(self.few, test_query_count=17)

    def test_many_matches_query_count(self):
        self.get_day(self.many, test_query_count=17)

    def test_forfeit_winner_choices(self):
        match = self.few[0]
        self.get_day(self.few)
        self.assertResponseContains(
            '<select name="matches-0-forfeit_winner" '
            + by_shell(
                workbook='class="wb-select" '
                'aria-describedby="id_matches-0-forfeit_winner_help" ',
                explorer='aria-describedby="id_matches-0-forfeit_winner_helptext" ',
            )
            + f'id="id_matches-0-forfeit_winner">'
            f'<option value="" selected>Double forfeit</option>'
            f'<option value="{match.home_team.pk}">{match.home_team.title}</option>'
            f'<option value="{match.away_team.pk}">{match.away_team.title}</option>'
            f"</select>"
        )

    def test_forfeit_saves_the_winner(self):
        match = self.few[0]
        data = {
            "matches-INITIAL_FORMS": "2",
            "matches-MAX_NUM_FORMS": "1000",
            "matches-TOTAL_FORMS": "2",
            "matches-0-id": str(match.pk),
            "matches-0-home_team_score": "0",
            "matches-0-away_team_score": "5",
            "matches-0-is_forfeit": "1",
            "matches-0-forfeit_winner": str(match.away_team.pk),
            "matches-1-id": str(self.few[1].pk),
            "byes-INITIAL_FORMS": "0",
            "byes-MAX_NUM_FORMS": "1000",
            "byes-TOTAL_FORMS": "0",
        }
        with self.login(self.superuser):
            self.post(
                "admin:fixja:match-results",
                self.season.competition.pk,
                self.season.pk,
                match.date.strftime("%Y%m%d"),
                data=data,
            )
        self.response_302()
        match.refresh_from_db()
        self.assertEqual(match.forfeit_winner, match.away_team)

    def test_forfeit_winner_must_be_one_of_the_teams(self):
        match = self.few[0]
        outsider = factories.TeamFactory.create(division=match.stage.division)
        data = {
            "matches-INITIAL_FORMS": "2",
            "matches-MAX_NUM_FORMS": "1000",
            "matches-TOTAL_FORMS": "2",
            "matches-0-id": str(match.pk),
            "matches-0-home_team_score": "0",
            "matches-0-away_team_score": "5",
            "matches-0-is_forfeit": "1",
            "matches-0-forfeit_winner": str(outsider.pk),
            "matches-1-id": str(self.few[1].pk),
            "byes-INITIAL_FORMS": "0",
            "byes-MAX_NUM_FORMS": "1000",
            "byes-TOTAL_FORMS": "0",
        }
        with self.login(self.superuser):
            self.post(
                "admin:fixja:match-results",
                self.season.competition.pk,
                self.season.pk,
                match.date.strftime("%Y%m%d"),
                data=data,
            )
        self.response_200()
        match.refresh_from_db()
        self.assertEqual(match.forfeit_winner, None)


class MatchDetailQueryTests(TestCase):
    """
    The detailed results page has a row for every player of both teams.
    Each row looked up its player and their statistics for the match on its
    own, so a full squad took well over a hundred queries. The same query
    budget now holds however many players the teams have.
    """

    def setUp(self):
        super().setUp()
        self.small = self._match(players=2)
        self.large = self._match(players=12)

    def _match(self, players):
        match = factories.MatchFactory.create(
            play_at=factories.GroundFactory.create(),
            home_team_score=players,
            away_team_score=0,
        )
        for team in (match.home_team, match.away_team):
            associations = factories.TeamAssociationFactory.create_batch(
                players, is_player=True, team=team, person__club=team.club
            )
        # The away team's players already have statistics entered.
        for association in associations:
            SimpleScoreMatchStatistic.objects.create(
                match=match, player=association.person, played=1, points=0
            )
        return match

    def get_detail(self, match, **kwargs):
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:competition:season:division:stage:match:detail",
                competition_id=match.stage.division.season.competition_id,
                season_id=match.stage.division.season_id,
                division_id=match.stage.division_id,
                stage_id=match.stage_id,
                match_id=match.pk,
                **kwargs,
            )

    # The tree in the rail opens the folders down to the match's pool.
    def test_small_squads_query_count(self):
        self.get_detail(self.small, test_query_count=26)

    def test_large_squads_query_count(self):
        self.get_detail(self.large, test_query_count=26)

    def test_entered_statistics_are_shown(self):
        self.get_detail(self.small)
        away = self.last_response.context["formsets"][1]
        self.assertEqual(
            [form.instance.pk is not None for form in away.forms], [True, True]
        )


class MatchRowMixin(IconMixin):
    """
    The menu of a match's row on its stage's Matches tab, and the run sheet's
    links to its statistics and referees pages.
    """

    detail = "admin:fixja:competition:season:division:stage:match:detail"
    referees = "admin:fixja:competition:season:division:stage:match:referees"

    def actions_cell(
        self, match, name, statistics=False, edit=True, delete=True, referees=True
    ):
        """
        The last cell of the match's row, named ``name``. Its menu offers
        Referees and Edit to those who may change the match, Statistics too
        when the players' statistics of the match can be entered, and Delete
        to those who may delete it.
        """
        namespace = "admin:fixja:competition:season:division:stage:match"
        args = match._get_url_args()
        referees_url = self.reverse(f"{namespace}:referees", *args)
        detail = self.reverse(f"{namespace}:detail", *args)
        edit_url = self.reverse(f"{namespace}:edit", *args)
        delete_url = self.reverse(f"{namespace}:delete", *args)
        csrf = (
            '<input type="hidden" name="csrfmiddlewaretoken" '
            f'value="{self.get_context("csrf_token")}">'
        )
        workbook_referees, explorer_referees = (
            (
                f'<li><a href="{referees_url}">{self.icon("flag")}Referees</a></li>',
                f'<a href="{referees_url}">{self.icon("referee")}Referees</a>',
            )
            if referees
            else ("", "")
        )
        workbook_statistics, explorer_statistics = (
            (
                f'<li><a href="{detail}">{self.icon("chart-bar")}Statistics</a></li>',
                f'<a href="{detail}">{self.icon("chart")}Statistics</a>',
            )
            if statistics
            else ("", "")
        )
        workbook_edit, explorer_edit = (
            (
                f'<li><a href="{edit_url}">{self.icon("pencil")}Edit</a></li>',
                f'<a href="{edit_url}">{self.icon("edit")}Edit</a>',
            )
            if edit
            else ("", "")
        )
        workbook_delete, explorer_delete = (
            (
                '<li class="wb-menu-last">'
                f'<form method="post" action="{delete_url}" '
                f'data-wb-confirm="The match “{name}” will be removed for good." '
                f'data-wb-confirm-title="Delete {name}?" '
                'data-wb-confirm-label="Delete match">'
                f'{csrf}<button type="submit" class="wb-danger-item">'
                f'{self.icon("trash-2")}Delete</button></form></li>',
                f'<form method="post" action="{delete_url}" '
                f'data-confirm="The match “{name}” will be removed for good." '
                'data-confirm-title="Delete this match?" data-confirm-label="Delete">'
                f'{csrf}<button type="submit" class="destructive-item">'
                f'{self.icon("trash")}Delete</button></form>',
            )
            if delete
            else ("", "")
        )
        return self.by_shell(
            workbook=(
                '<td class="wb-row-actions"><div class="wb-row-buttons">'
                '<button type="button" class="wb-button wb-button-quiet '
                'wb-button-icon wb-button-small wb-menu-button" '
                f'popovertarget="wbm-match-{match.pk}" aria-expanded="false" '
                f'aria-label="More actions for {name}">{self.icon("ellipsis")}'
                "</button>"
                f'<div class="wb-menu" popover id="wbm-match-{match.pk}"><ul>'
                f"{workbook_referees}{workbook_statistics}{workbook_edit}"
                f"{workbook_delete}</ul></div></div></td>"
            ),
            explorer=(
                '<td class="actions-cell"><div class="row-actions"><div class="menu">'
                '<button type="button" class="button quiet icon-only compact" '
                'data-popover aria-expanded="false" '
                f'aria-controls="row-menu-match-{match.pk}">{self.icon("more")}'
                f'<span class="visually-hidden">More actions for {name}</span>'
                "</button>"
                f'<div class="menu-panel" id="row-menu-match-{match.pk}">'
                f"{explorer_referees}{explorer_statistics}{explorer_edit}"
                f"{explorer_delete}</div></div></div></td>"
            ),
        )

    def statistics_link(self, match):
        """The run sheet's link to the match's statistics page."""
        url = self.reverse(self.detail, *match._get_url_args())
        return self.by_shell(
            workbook=f'<a href="{url}">{self.icon("chart-bar")}Detail</a>',
            explorer=f'<a href="{url}">Statistics</a>',
        )

    def back_to_sheet(self, name, match):
        """
        The URL of the match's page ``name``, which sends the person back to
        the run sheet of the match's day.
        """
        season = match.stage.division.season
        sheet = self.reverse(
            "admin:fixja:match-runsheet",
            season.competition_id,
            season.pk,
            f"{match.date:%Y%m%d}",
        )
        namespace = "admin:fixja:competition:season:division:stage:match"
        # The sheet writes its own path after "?next=" as it is, which
        # reverse(query=) would percent-encode.
        url = self.reverse(f"{namespace}:{name}", *match._get_url_args())
        return f"{url}?next={sheet}"

    def resync_link(self, match):
        """The run sheet's link that re-pushes the match's broadcast to YouTube."""
        url = self.back_to_sheet("resync-live-stream", match)
        return self.by_shell(
            workbook=f'<a href="{url}">{self.icon("refresh-cw")}Resync</a>',
            explorer=f'<a href="{url}">Resync</a>',
        )

    def stream_link(self, match, icon, label):
        """
        The Workbook run sheet's link to the match's page about its stream:
        "Fix stream" for a broadcast without a stream key, "Stream?" for a
        match on a camera ground that is not being streamed.
        """
        url = self.back_to_sheet("edit", match)
        return f'<a href="{url}">{self.icon(icon)}{label}</a>'

    def referees_link(self, match):
        """
        The run sheet's link to the match's referees page, which sends the
        person back to the sheet.
        """
        url = self.back_to_sheet("referees", match)
        return self.by_shell(
            workbook=f'<a href="{url}">{self.icon("flag")}Referees</a>',
            explorer=f'<a href="{url}">Referees</a>',
        )

class MatchUrlsTests(TestCase):
    """A match names its pages in the admin, its statistics page among them."""

    def test_detail_is_the_statistics_page(self):
        match = factories.MatchFactory.create()
        self.assertEqual(
            str(match.urls["detail"]),
            self.reverse(
                "admin:fixja:competition:season:division:stage:match:detail",
                *match._get_url_args(),
            ),
        )


@per_shell
class MatchDetailNotReadyTests(MatchRowMixin, TestCase):
    """
    The players' statistics of a match are entered once both teams are known
    and the result is in: each side's points must add up to its score. Until
    then the statistics page sends the person to the match's page with a
    message saying why, and neither the run sheet nor the match's row menu
    links to it.
    """

    def setUp(self):
        super().setUp()
        self.stage = factories.StageFactory.create()

    def match(self, **kwargs):
        return factories.MatchFactory.create(
            stage=self.stage, date=date(2025, 5, 1), **kwargs
        )

    def assertSentToMatch(self, match):
        self.assert_http_302_found(url=str(match.urls["edit"]))
        self.assertResponseMessages(
            [
                messages.Message(
                    messages.WARNING,
                    "Player statistics can be entered once both teams are "
                    "known and the result is in.",
                )
            ]
        )

    def test_match_without_result(self):
        match = self.match()
        with self.login(self.superuser):
            self.get(self.detail, *match._get_url_args())
        self.assertSentToMatch(match)

    def test_bye(self):
        match = self.match(is_bye=True, away_team=None, bye_processed=True)
        with self.login(self.superuser):
            self.get(self.detail, *match._get_url_args())
        self.assertSentToMatch(match)

    def test_undecided_team(self):
        # The scores are in, so only the team still to be decided stops it.
        match = self.match(
            home_team=None,
            home_team_undecided=factories.UndecidedTeamFactory.create(
                stage=self.stage
            ),
            home_team_score=2,
            away_team_score=1,
        )
        with self.login(self.superuser):
            self.get(self.detail, *match._get_url_args())
        self.assertSentToMatch(match)

    def test_post_saves_nothing(self):
        match = self.match()
        factories.TeamAssociationFactory.create(
            is_player=True, team=match.home_team, person__club=match.home_team.club
        )
        data = {
            "home-TOTAL_FORMS": "1",
            "home-INITIAL_FORMS": "1",
            "home-MAX_NUM_FORMS": "1000",
            "home-0-id": "",
            "home-0-number": "7",
            "home-0-played": "1",
            "home-0-points": "0",
            "home-0-mvp": "0",
            "away-TOTAL_FORMS": "0",
            "away-INITIAL_FORMS": "0",
            "away-MAX_NUM_FORMS": "1000",
        }
        with self.login(self.superuser):
            self.post(self.detail, *match._get_url_args(), data=data)
        self.assertSentToMatch(match)
        self.assertCountEqual(match.statistics.all(), [])

    def test_run_sheet_links_only_matches_with_a_result(self):
        played = self.match(home_team_score=3, away_team_score=1)
        unplayed = self.match()
        season = self.stage.division.season
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:match-runsheet",
                season.competition_id,
                season.pk,
                "20250501",
            )
        self.assertResponseContains(self.statistics_link(played), count=1)
        self.assertResponseContains(self.statistics_link(unplayed), count=0)

    def test_row_menu_offers_statistics_only_with_a_result(self):
        played = self.match(
            home_team__title="Leopards",
            away_team__title="Marlins",
            home_team_score=3,
            away_team_score=1,
        )
        unplayed = self.match(home_team__title="Sharks", away_team__title="Eagles")
        bye = self.match(
            home_team__title="Hawks", is_bye=True, away_team=None, bye_processed=True
        )
        undecided = self.match(
            home_team=None,
            home_team_undecided=factories.UndecidedTeamFactory.create(
                stage=self.stage, label="Winner SF1"
            ),
            away_team__title="Lions",
            home_team_score=2,
            away_team_score=1,
        )
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:competition:season:division:stage:edit",
                *self.stage._get_url_args(),
            )
        self.assertResponseContains(
            self.actions_cell(played, "Leopards vs Marlins", statistics=True)
        )
        self.assertResponseContains(self.actions_cell(unplayed, "Sharks vs Eagles"))
        self.assertResponseContains(self.actions_cell(bye, "Hawks vs Bye"))
        self.assertResponseContains(self.actions_cell(undecided, "Winner SF1 vs Lions"))


@per_shell
class MatchDetailPermissionTests(MatchRowMixin, TestCase):
    """
    The players' statistics of a match are entered by whoever may change the
    match: ``change_match`` on the match, or on every match, as the match's
    own page asks. The statistics page refuses anyone else, and the row menu
    and the run sheet offer it only to those who may open it.
    """

    user_factory = StaffFactory

    def setUp(self):
        super().setUp()
        self.stage = factories.StageFactory.create()
        self.staff = self.make_user("staff")

    def match(self, **kwargs):
        """A match on 1 May 2025 with its result in, 3-0 to the home side."""
        return factories.MatchFactory.create(
            **{
                "stage": self.stage,
                "date": date(2025, 5, 1),
                "home_team_score": 3,
                "away_team_score": 0,
                **kwargs,
            }
        )

    def statistics(self, match):
        """One home player, who scored the home side's three points."""
        factories.TeamAssociationFactory.create(
            is_player=True, team=match.home_team, person__club=match.home_team.club
        )
        return {
            "home-TOTAL_FORMS": "1",
            "home-INITIAL_FORMS": "1",
            "home-MAX_NUM_FORMS": "1000",
            "home-0-id": "",
            "home-0-number": "7",
            "home-0-played": "1",
            "home-0-points": "3",
            "home-0-mvp": "0",
            "away-TOTAL_FORMS": "0",
            "away-INITIAL_FORMS": "0",
            "away-MAX_NUM_FORMS": "1000",
        }

    def test_login_required(self):
        match = self.match()
        self.assertLoginRequired(self.detail, *match._get_url_args())

    def test_staff_without_change_match_is_refused(self):
        match = self.match()
        data = self.statistics(match)
        with self.login(self.staff):
            self.get(self.detail, *match._get_url_args())
            self.assert_http_403_forbidden()
            self.post(self.detail, *match._get_url_args(), data=data)
            self.assert_http_403_forbidden()
        self.assertCountEqual(match.statistics.all(), [])

    def test_change_match_on_another_match_is_refused(self):
        match = self.match()
        assign_perm("competition.change_match", self.staff, self.match())
        with self.login(self.staff):
            self.get(self.detail, *match._get_url_args())
            self.assert_http_403_forbidden()

    def test_refused_before_the_result_is_looked_at(self):
        # Someone who may not change the match is refused, not sent to the
        # match's page to be told its result is not in.
        match = self.match(home_team_score=None, away_team_score=None)
        with self.login(self.staff):
            self.get(self.detail, *match._get_url_args())
            self.assert_http_403_forbidden()

    def test_change_match_on_the_match_enters_statistics(self):
        match = self.match()
        data = self.statistics(match)
        assign_perm("competition.change_match", self.staff, match)
        with self.login(self.staff):
            self.get(self.detail, *match._get_url_args())
            self.assert_http_200_ok()
            self.post(self.detail, *match._get_url_args(), data=data)
            self.assert_http_302_found(url=self.reverse("admin:index"))
        self.assertEqual(match.statistics.get().points, 3)

    def test_change_match_on_every_match_opens_the_page(self):
        match = self.match()
        assign_perm("competition.change_match", self.staff)
        with self.login(self.staff):
            self.get(self.detail, *match._get_url_args())
            self.assert_http_200_ok()

    def test_row_menu_offers_statistics_to_those_who_may_change_the_match(self):
        # The stage's Matches tab lists the matches the person may act on at
        # all. They may change the first and delete the second, so both rows
        # are drawn, and Statistics is offered with Edit, not with Delete.
        theirs = self.match(home_team__title="Leopards", away_team__title="Marlins")
        other = self.match(home_team__title="Sharks", away_team__title="Eagles")
        assign_perm("competition.change_stage", self.staff, self.stage)
        assign_perm("competition.change_match", self.staff, theirs)
        assign_perm("competition.delete_match", self.staff, other)
        with self.login(self.staff):
            self.get_check_200(
                "admin:fixja:competition:season:division:stage:edit",
                *self.stage._get_url_args(),
            )
        self.assertResponseContains(
            self.actions_cell(
                theirs, "Leopards vs Marlins", statistics=True, delete=False
            )
        )
        self.assertResponseContains(
            self.actions_cell(other, "Sharks vs Eagles", edit=False, referees=False)
        )

    def test_run_sheet_offers_statistics_to_those_who_may_change_the_match(self):
        theirs = self.match(home_team__title="Leopards")
        other = self.match(home_team__title="Sharks")
        assign_perm("competition.change_match", self.staff, theirs)
        season = self.stage.division.season
        # The sheet asks for the person's permissions on the day's matches
        # once, not once a row; and a row with neither link does not walk to
        # its competition for their URLs.
        with (
            self.login(self.staff),
            self.assertNumQueries(self.by_shell(workbook=21, explorer=21)),
        ):
            self.get_check_200(
                "admin:fixja:match-runsheet",
                season.competition_id,
                season.pk,
                "20250501",
            )
        self.assertResponseContains(self.statistics_link(theirs), count=1)
        # The other match is on the sheet, without the link.
        self.assertResponseContains(
            self.by_shell(
                workbook="<td>Sharks <strong>3</strong></td>",
                explorer='<td class="team">Sharks <strong>3</strong></td>',
            )
        )
        self.assertResponseContains(self.statistics_link(other), count=0)


@per_shell
class RefereeAppointmentsPermissionTests(MatchRowMixin, TestCase):
    """
    A match's referees are appointed by whoever may change the match, which is
    what its referees page asks. The row menu and the run sheet offer the page
    only to those who may open it.
    """

    user_factory = StaffFactory

    def setUp(self):
        super().setUp()
        self.stage = factories.StageFactory.create()
        self.staff = self.make_user("staff")

    def match(self, **kwargs):
        """A match on 1 May 2025, yet to be played."""
        return factories.MatchFactory.create(
            stage=self.stage, date=date(2025, 5, 1), **kwargs
        )

    def test_staff_without_change_match_is_refused(self):
        match = self.match()
        with self.login(self.staff):
            self.get(self.referees, *match._get_url_args())
            self.assert_http_403_forbidden()

    def test_change_match_on_the_match_opens_the_page(self):
        match = self.match()
        assign_perm("competition.change_match", self.staff, match)
        with self.login(self.staff):
            self.get_check_200(self.referees, *match._get_url_args())

    def test_row_menu_offers_referees_to_those_who_may_change_the_match(self):
        # The stage's Matches tab lists the matches the person may act on at
        # all. They may change the first and delete the second, so both rows
        # are drawn, and Referees is offered with Edit, not with Delete.
        theirs = self.match(home_team__title="Leopards", away_team__title="Marlins")
        other = self.match(home_team__title="Sharks", away_team__title="Eagles")
        assign_perm("competition.change_stage", self.staff, self.stage)
        assign_perm("competition.change_match", self.staff, theirs)
        assign_perm("competition.delete_match", self.staff, other)
        with self.login(self.staff):
            self.get_check_200(
                "admin:fixja:competition:season:division:stage:edit",
                *self.stage._get_url_args(),
            )
        self.assertResponseContains(
            self.actions_cell(theirs, "Leopards vs Marlins", delete=False)
        )
        self.assertResponseContains(
            self.actions_cell(other, "Sharks vs Eagles", edit=False, referees=False)
        )

    def test_run_sheet_offers_referees_to_those_who_may_change_the_match(self):
        theirs = self.match(home_team__title="Leopards")
        other = self.match(home_team__title="Sharks")
        assign_perm("competition.change_match", self.staff, theirs)
        season = self.stage.division.season
        # The gate reads the permissions the sheet asks for once for the day's
        # matches, and the row without the link does not walk to its
        # competition for the URL: two queries fewer than when every row did.
        with self.login(self.staff), self.assertNumQueries(21):
            self.get_check_200(
                "admin:fixja:match-runsheet",
                season.competition_id,
                season.pk,
                "20250501",
            )
        self.assertResponseContains(self.referees_link(theirs), count=1)
        # The other match is on the sheet, without the link.
        self.assertResponseContains(
            self.by_shell(
                workbook="<td>Sharks</td>", explorer='<td class="team">Sharks</td>'
            )
        )
        self.assertResponseContains(self.referees_link(other), count=0)


class StreamedMatchMixin(MatchRowMixin):
    """A season set up to stream to YouTube, with a camera on one ground."""

    user_factory = StaffFactory

    def setUp(self):
        super().setUp()
        self.stage = factories.StageFactory.create(
            division__season__live_stream=True,
            division__season__live_stream_project_id="test-project-123",
            division__season__live_stream_client_id="test-client-id",
            division__season__live_stream_client_secret="test-client-secret",
        )
        self.camera = factories.GroundFactory.create(
            venue__season=self.stage.division.season, live_stream=True
        )
        self.staff = self.make_user("staff")
        # YouTube's broadcast identifiers are unique.
        self.broadcasts = count(1)

    def match(self, **kwargs):
        """A match on the camera ground at 14:00 UTC on 1 May 2025."""
        return factories.MatchFactory.create(
            **{
                "stage": self.stage,
                "play_at": self.camera,
                "date": date(2025, 5, 1),
                "time": time(14, 0),
                "datetime": datetime(2025, 5, 1, 14, 0, tzinfo=ZoneInfo("UTC")),
                **kwargs,
            }
        )

    def streamed(self, **kwargs):
        """A match whose broadcast is scheduled and bound to a stream key."""
        return self.match(
            live_stream=True,
            live_stream_bind="yt-bound-abc",
            external_identifier=f"yt-broadcast-{next(self.broadcasts)}",
            **kwargs,
        )

    def get_run_sheet(self, queries):
        """The run sheet of 1 May 2025, as the member of staff sees it."""
        season = self.stage.division.season
        # guardian looks up the matches' content type once a process and
        # keeps it, so look it up first: the count must not depend on which
        # test runs first.
        ContentType.objects.get_for_model(Match)
        with self.login(self.staff), self.assertNumQueries(queries):
            self.get_check_200(
                "admin:fixja:match-runsheet",
                season.competition_id,
                season.pk,
                "20250501",
            )


@per_shell
class ResyncLiveStreamPermissionTests(MessagesTestMixin, StreamedMatchMixin, TestCase):
    """
    A match's broadcast is re-pushed to YouTube by whoever may change the
    match, as its own page asks. The resync page refuses anyone else, and the
    run sheet offers Resync only to those who may use it.
    """

    resync = "admin:fixja:competition:season:division:stage:match:resync-live-stream"

    def test_login_required(self):
        match = self.streamed()
        self.assertLoginRequired(self.resync, *match._get_url_args())

    @patch("tournamentcontrol.competition.admin.sync_live_stream")
    def test_staff_without_change_match_is_refused(self, mock_sync_live_stream):
        match = self.streamed()
        with self.login(self.staff):
            self.get(self.resync, *match._get_url_args())
            self.assert_http_403_forbidden()
            self.post(self.resync, *match._get_url_args())
            self.assert_http_403_forbidden()
        mock_sync_live_stream.s.assert_not_called()

    @patch("tournamentcontrol.competition.admin.sync_live_stream")
    def test_change_match_on_another_match_is_refused(self, mock_sync_live_stream):
        match = self.streamed()
        assign_perm("competition.change_match", self.staff, self.streamed())
        with self.login(self.staff):
            self.post(self.resync, *match._get_url_args())
            self.assert_http_403_forbidden()
        mock_sync_live_stream.s.assert_not_called()

    @patch("tournamentcontrol.competition.admin.sync_live_stream")
    def test_change_match_on_the_match_queues_the_resync(self, mock_sync_live_stream):
        match = self.streamed()
        assign_perm("competition.change_match", self.staff, match)
        with self.login(self.staff):
            self.get(self.resync, *match._get_url_args())
            self.assert_http_200_ok()
            self.post(self.resync, *match._get_url_args())
            self.assert_http_302_found(url=str(self.stage.urls["edit"]))
        self.assertResponseMessages(
            [
                messages.Message(
                    messages.SUCCESS, "YouTube live stream resync has been queued."
                )
            ]
        )
        mock_sync_live_stream.s.assert_called_once_with(match.pk, base_url=ANY)
        mock_sync_live_stream.s.return_value.apply_async.assert_called_once_with()

    def test_change_match_on_every_match_opens_the_page(self):
        match = self.streamed()
        assign_perm("competition.change_match", self.staff)
        with self.login(self.staff):
            self.get_check_200(self.resync, *match._get_url_args())

    def test_run_sheet_offers_resync_to_those_who_may_change_the_match(self):
        theirs = self.streamed(home_team__title="Leopards")
        other = self.streamed(home_team__title="Sharks")
        assign_perm("competition.change_match", self.staff, theirs)
        # The gate reads the permissions the sheet asks for once for the day's
        # matches. The row without the links does not walk to its competition
        # for their URLs, and under Workbook does not ask whether its ground
        # has a camera; the sheet's other per-row queries (stage, division,
        # place, referees) are older than the gate.
        self.get_run_sheet(self.by_shell(workbook=24, explorer=23))
        self.assertResponseContains(self.resync_link(theirs), count=1)
        # The other match is on the sheet, without the link.
        self.assertResponseContains(
            self.by_shell(
                workbook="<td>Sharks</td>", explorer='<td class="team">Sharks</td>'
            )
        )
        self.assertResponseContains(self.resync_link(other), count=0)


@per_shell(shells=("workbook",))
class StreamLinksPermissionTests(StreamedMatchMixin, TestCase):
    """
    The Workbook run sheet's "Fix stream" and "Stream?" links open the match's
    page, which asks for ``change_match``, so they are offered only to those
    who may change the match. The Explorer sheet has no such links.
    """

    def test_fix_stream_is_offered_to_those_who_may_change_the_match(self):
        # Streaming, but not yet bound to a stream key.
        theirs = self.match(live_stream=True, home_team__title="Leopards")
        other = self.match(live_stream=True, home_team__title="Sharks")
        assign_perm("competition.change_match", self.staff, theirs)
        # Neither row asks whether its ground has a camera: it is streaming.
        self.get_run_sheet(23)
        self.assertResponseContains(
            self.stream_link(theirs, "triangle-alert", "Fix stream"), count=1
        )
        self.assertResponseContains("<td>Sharks</td>")
        self.assertResponseContains(
            self.stream_link(other, "triangle-alert", "Fix stream"), count=0
        )

    def test_stream_prompt_is_offered_to_those_who_may_change_the_match(self):
        # On a camera ground, not streamed.
        theirs = self.match(home_team__title="Leopards")
        other = self.match(home_team__title="Sharks")
        assign_perm("competition.change_match", self.staff, theirs)
        # Only the row that may offer the link asks whether its ground has a
        # camera.
        self.get_run_sheet(24)
        self.assertResponseContains(
            self.stream_link(theirs, "pencil", "Stream?"), count=1
        )
        self.assertResponseContains("<td>Sharks</td>")
        self.assertResponseContains(
            self.stream_link(other, "pencil", "Stream?"), count=0
        )


@per_shell(shells=("explorer",))
class MatchPageStatisticsTests(IconMixin, TestCase):
    """
    Explorer's page of a match has a Statistics button beside Referees once
    the players' statistics of the match can be entered: both teams are known
    and the result is in. A bye never has one. The page itself, and so the
    button, is for those who may change the match.
    """

    namespace = "admin:fixja:competition:season:division:stage:match"
    user_factory = StaffFactory

    def button(self, match, name, icon, label):
        url = self.reverse(f"{self.namespace}:{name}", *match._get_url_args())
        return (
            f'<a class="button quiet" href="{url}">{self.icon(icon)}'
            f"<span>{label}</span></a>"
        )

    def get_match_page(self, **kwargs):
        match = factories.MatchFactory.create(**kwargs)
        with self.login(self.superuser):
            self.get_check_200(f"{self.namespace}:edit", *match._get_url_args())
        self.assertResponseContains(
            self.button(match, "referees", "referee", "Referees")
        )
        return match

    def test_match_with_a_result(self):
        match = self.get_match_page(home_team_score=3, away_team_score=1)
        self.assertResponseContains(
            self.button(match, "detail", "chart", "Statistics"), count=1
        )

    def test_match_without_a_result(self):
        match = self.get_match_page()
        self.assertResponseContains(
            self.button(match, "detail", "chart", "Statistics"), count=0
        )

    def test_bye(self):
        match = self.get_match_page(is_bye=True, away_team=None, bye_processed=True)
        self.assertResponseContains(
            self.button(match, "detail", "chart", "Statistics"), count=0
        )

    def test_undecided_team(self):
        stage = factories.StageFactory.create()
        match = self.get_match_page(
            stage=stage,
            home_team=None,
            home_team_undecided=factories.UndecidedTeamFactory.create(stage=stage),
            home_team_score=2,
            away_team_score=1,
        )
        self.assertResponseContains(
            self.button(match, "detail", "chart", "Statistics"), count=0
        )

    def test_change_match_on_the_match_shows_the_button(self):
        match = factories.MatchFactory.create(home_team_score=3, away_team_score=1)
        staff = self.make_user("staff")
        assign_perm("competition.change_match", staff, match)
        with self.login(staff):
            self.get_check_200(f"{self.namespace}:edit", *match._get_url_args())
        self.assertResponseContains(
            self.button(match, "detail", "chart", "Statistics"), count=1
        )

    def test_without_change_match_the_page_is_refused(self):
        match = factories.MatchFactory.create(home_team_score=3, away_team_score=1)
        with self.login(self.make_user("staff")):
            self.get(f"{self.namespace}:edit", *match._get_url_args())
            self.assert_http_403_forbidden()


class DashboardQueryTests(TestCase):
    """
    The dashboard lists matches awaiting results and the stages with
    reports to print. Each report row looked up its division, season and
    competition on its own. The same query budget now holds however many
    stages need reports.
    """

    def _stages(self, count):
        season = factories.SeasonFactory.create()
        for _ in range(count):
            stage = factories.StageFactory.create(division__season=season)
            stage.matches_needing_printing.add(
                factories.MatchFactory.create(stage=stage)
            )

    def get_dashboard(self, **kwargs):
        with self.login(self.superuser):
            self.assertGoodView("admin:index", **kwargs)

    def test_few_stages_query_count(self):
        self._stages(2)
        self.get_dashboard(test_query_count=DASHBOARD_QUERIES)

    def test_many_stages_query_count(self):
        self._stages(8)
        self.get_dashboard(test_query_count=DASHBOARD_QUERIES)


class MostValuableWidgetTests(TestCase):
    """
    The "Awaiting MVP Points" widget lists the matches where a team's
    players have statistics but no MVP points. Each row it listed looked up
    its teams, clubs, stage, division, season and competition on its own, so
    the dashboard made more queries the more seasons were waiting. The same
    query budget now holds however many seasons and matches are listed.
    """

    def _season(self, matches=2, divisions=2, **kwargs):
        season = factories.SeasonFactory.create(**kwargs)
        listed = []
        for _ in range(divisions):
            stage = factories.StageFactory.create(division__season=season)
            for _ in range(matches):
                listed.append(self._match(stage, home_mvp=0, away_mvp=1))
        return listed

    def _match(self, stage, home_mvp, away_mvp):
        match = factories.MatchFactory.create(
            stage=stage, home_team_score=3, away_team_score=1
        )
        for team, mvp in ((match.home_team, home_mvp), (match.away_team, away_mvp)):
            association = factories.TeamAssociationFactory.create(
                team=team, person__club=team.club, is_player=True
            )
            SimpleScoreMatchStatistic.objects.create(
                match=match,
                player=association.person,
                number=1,
                played=1,
                points=0,
                mvp=mvp,
            )
        return match

    def get_dashboard(self, **kwargs):
        with self.login(self.superuser):
            self.assertGoodView("admin:index", **kwargs)

    def dashboard_queries(self):
        with self.login(self.superuser):
            with CaptureQueriesContext(connection) as queries:
                self.get("admin:index")
            self.response_200()
        return len(queries)

    def test_few_seasons_query_count(self):
        self._season()
        self.get_dashboard(test_query_count=DASHBOARD_QUERIES + 1)

    def test_many_seasons_query_count(self):
        for _ in range(6):
            self._season(matches=4)
        self.get_dashboard(test_query_count=DASHBOARD_QUERIES + 1)

    def test_query_count_does_not_grow(self):
        self._season()
        few = self.dashboard_queries()
        for _ in range(5):
            self._season(matches=4)
        self.assertEqual(self.dashboard_queries(), few)

    def test_matches_listed(self):
        listed = self._season(matches=1, divisions=1)
        # A completed season whose MVP results have no publish time is
        # still listed, as it always has been.
        listed += self._season(
            matches=1, divisions=1, complete=True, mvp_results_public=None
        )
        # A completed season whose MVP results have a publish time is not.
        self._season(
            matches=1,
            divisions=1,
            complete=True,
            mvp_results_public=datetime(2020, 1, 1, tzinfo=ZoneInfo("UTC")),
        )
        # Nor is a stage that does not keep MVP points, a match where both
        # teams have MVP points, or one where none were entered at all.
        season = factories.SeasonFactory.create()
        self._match(
            factories.StageFactory.create(division__season=season, keep_mvp=False),
            home_mvp=0,
            away_mvp=0,
        )
        stage = factories.StageFactory.create(division__season=season)
        self._match(stage, home_mvp=1, away_mvp=2)
        self._match(stage, home_mvp=None, away_mvp=None)

        self.assertCountEqual(
            [match.pk for match in MostValuableWidget().matches],
            [match.pk for match in listed],
        )

    def test_listed_match_links_to_match(self):
        (match,) = self._season(matches=1, divisions=1)
        self.get_dashboard()
        url = reverse(
            "admin:fixja:competition:season:division:stage:match:detail",
            args=(
                match.stage.division.season.competition_id,
                match.stage.division.season_id,
                match.stage.division_id,
                match.stage_id,
                match.pk,
            ),
        )
        self.assertResponseContains(
            f'<a class="{by_shell(workbook="wb-button wb-button-small", explorer="button compact")}" '
            f'href="{url}">Enter</a>'
        )


class WizardBrandTests(TestCase):
    """
    The wizards render through SessionWizardView, not AdminComponentMixin.render,
    so the shell must brand them without the context processor's help.
    """

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND=None)
    def test_draw_generation_wizard_is_branded_without_the_context_processor(self):
        stage = factories.StageFactory.create(
            division__season__mode=DAILY, division__games_per_day=1
        )
        factories.TeamFactory.create_batch(4, division=stage.division)
        build_url = stage.url_names["build"]

        templates = copy.deepcopy(settings.TEMPLATES)
        processors = templates[0]["OPTIONS"]["context_processors"]
        processors.remove("touchtechnology.admin.context_processors.brand")

        with self.settings(TEMPLATES=templates), self.login(self.superuser):
            self.get(build_url.url_name, *build_url.args)
            self.response_200()
            self.assertNotIn("brand", self.last_response.context_data)
            self.assertResponseContains(
                by_shell(
                    workbook=f"<title>Build the draw &middot; {stage.title} "
                    "&middot; Administration</title>",
                    explorer=f"<title>{stage.title} \u2013 Administration</title>",
                ),
            )
            self.assertResponseContains(
                "<style>:root{--brand-primary:#275d8b;--brand-secondary:#e8862a;"
                "--brand-success:#2a8a5c;--brand-warning:#d9a21b;"
                "--brand-danger:#b8322f;}</style>",
            )
            self.assertResponseContains(
                by_shell(
                    workbook='<a class="wb-brand" href="/admin/">'
                    '<img class="wb-brand-logo" src="/static/img/logo.png" alt="">'
                    '<span class="wb-brand-name">Administration</span></a>',
                    explorer='<img src="/static/img/logo.png" alt="Administration">',
                ),
            )


@per_shell
class ByeMatchTests(MatchRowMixin, TestCase):
    """
    A bye match is named in plain text, "Bye vs Marlins". The admin puts the
    name of a match where markup is not read as markup: the label of the
    button that opens its row's menu, the words of the delete confirmation and
    the title of its own page.
    """

    def setUp(self):
        super().setUp()
        self.stage = factories.StageFactory.create(title="Regular Season")
        self.args = (
            self.stage.division.season.competition_id,
            self.stage.division.season_id,
            self.stage.division_id,
            self.stage.pk,
        )

    def bye(self, **kwargs):
        return factories.MatchFactory.create(stage=self.stage, is_bye=True, **kwargs)

    def results(self, **teams):
        """The results page of the day of a bye, with only the bye to process."""
        bye = self.bye(date=date(2026, 10, 8), time=None, datetime=None, **teams)
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:match-results", *self.args[:2], f"{bye.date:%Y%m%d}"
            )
        return bye

    def bye_row(self, bye, team):
        """The bye's row on the results page, named for the team with the bye."""
        division = self.stage.division.title
        key = (
            f'<input type="hidden" name="byes-0-id" value="{bye.pk}" id="id_byes-0-id">'
        )
        attrs = self.by_shell(
            workbook='class="wb-select"', explorer='placeholder="Bye processed"'
        )
        select = (
            f'<select name="byes-0-bye_processed" {attrs} id="id_byes-0-bye_processed">'
            '<option value="1">Yes</option><option value="0" selected>No</option>'
            "</select>"
        )
        return self.by_shell(
            workbook=(
                f'<div class="wb-row-form">{key}'
                '<div class="wb-field wb-field-select select"><div class="wb-label">'
                '<label class="field_name" for="id_byes-0-bye_processed">'
                f"{team}</label></div>"
                f'<div class="wb-control-wrap">{select}</div></div>'
                f'<p class="wb-help">{division}</p></div>'
            ),
            explorer=(
                f'<li class="bye">{key}<label for="id_byes-0-bye_processed">{team} '
                f'<small class="muted">{division}</small></label>{select}</li>'
            ),
        )

    def test_a_bye_at_home_is_named_in_its_row(self):
        match = self.bye(home_team=None, away_team__title="Marlins")
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:competition:season:division:stage:edit", *self.args
            )
        self.assertResponseContains(
            self.by_shell(
                workbook='<td data-label="Home">Bye</td>', explorer="<td>Bye</td>"
            ),
        )
        self.assertResponseContains(self.actions_cell(match, "Bye vs Marlins"))

    def test_a_bye_away_is_named_in_its_row(self):
        match = self.bye(home_team__title="Leopards", away_team=None)
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:competition:season:division:stage:edit", *self.args
            )
        self.assertResponseContains(
            self.by_shell(
                workbook='<td data-label="Away">Bye</td>', explorer="<td>Bye</td>"
            ),
        )
        self.assertResponseContains(self.actions_cell(match, "Leopards vs Bye"))

    def test_the_page_of_a_bye_is_titled_in_plain_text(self):
        match = self.bye(home_team=None, away_team__title="Marlins")
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:competition:season:division:stage:match:edit",
                *self.args,
                match.pk,
            )
        brand = get_brand().name
        self.assertResponseContains(
            self.by_shell(
                workbook=f"<title>Bye vs Marlins &middot; {brand}</title>",
                explorer=f"<title>Regular Season &ndash; {brand}</title>",
            ),
        )
        self.assertResponseContains("<h1>Bye vs Marlins</h1>")

    def test_the_results_page_names_the_home_team_of_a_bye_away(self):
        bye = self.results(home_team__title="Leopards", away_team=None)
        self.assertResponseContains(self.bye_row(bye, "Leopards"))

    def test_the_results_page_names_the_away_team_of_a_bye_at_home(self):
        bye = self.results(home_team=None, away_team__title="Marlins")
        self.assertResponseContains(self.bye_row(bye, "Marlins"))
