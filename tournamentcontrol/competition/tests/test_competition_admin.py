import unittest
from datetime import date, datetime, time
from unittest import mock
from zoneinfo import ZoneInfo

from dateutil.rrule import DAILY
from django import VERSION
from django.contrib import messages
from django.template import Context, Template
from django.urls import reverse
from test_plus import TestCase as BaseTestCase

from touchtechnology.admin.mixins import AdminUrlLookup
from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.models import (
    Division,
    Ground,
    Match,
    Stage,
    StageGroup,
    Team,
)
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.utils import round_robin, round_robin_format

try:
    from django.contrib.messages.test import MessagesTestMixin
except ImportError:  # Django < 5.0
    from tournamentcontrol.competition.tests.test_utils import (
        MessagesTestMixin,
    )


class TestCase(BaseTestCase):
    def setUp(self):
        super(TestCase, self).setUp()
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
        self.assertGoodEditView("%s:add" % namespace, *args[:-1], **kwargs)
        self.assertGoodEditView("%s:edit" % namespace, *args, **kwargs)
        self.assertGoodDeleteView("%s:delete" % namespace, *args)


class TemplateTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super(TemplateTests, cls).setUpClass()
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
        super(TemplateTests, cls).tearDownClass()

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
            self.assertResponseContains('<td class="team">1st</td>')
            self.assertResponseContains(
                '<td class="team">2nd </td>'
            )  # whitespace deliberate
            self.assertResponseContains(
                '<td class="team">Chees&eacute;&nbsp;&amp;&nbsp;Crackers</td>'
            )

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
            self.assertResponseContains(
                "<h4>%s<br /><small>%s</small></h4>" % (self.division, self.stage)
            )
            self.assertResponseContains(
                "<p>1st <br>2nd</p>"
            )  # whitespace & br style deliberate
            self.assertResponseContains(
                "<p>Chees&eacute;&nbsp;&amp;&nbsp;Crackers<br>4th</p>"
            )


class GoodViewTests(TestCase):
    def test_reorder_down(self):
        stage = factories.StageFactory.create()
        pool_a, pool_b, pool_c = factories.StageGroupFactory.create_batch(
            stage=stage, size=3
        )

        with self.login(self.superuser):
            # Without a HTTP_REFERER set this should throw a 404
            self.get("admin:fixja:reorder", "stagegroup", pool_b.pk, "down")
            self.response_404()

            # The first time we try to shift this down it will work because it
            # isn't last in it's set.
            self.get(
                "admin:fixja:reorder",
                "stagegroup",
                pool_b.pk,
                "down",
                extra=dict(HTTP_REFERER="http://testserver/"),
            )
            self.response_302()

            # This time, however, it should fail because we're now last.
            self.get(
                "admin:fixja:reorder",
                "stagegroup",
                pool_b.pk,
                "down",
                extra=dict(HTTP_REFERER="http://testserver/"),
            )
            self.response_404()

    def test_reorder_up(self):
        stage = factories.StageFactory.create()
        pool_a, pool_b, pool_c = factories.StageGroupFactory.create_batch(
            stage=stage, size=3
        )

        with self.login(self.superuser):
            # Without a HTTP_REFERER set this should throw a 404
            self.get("admin:fixja:reorder", "stagegroup", pool_b.pk, "up")
            self.response_404()

            # The first time we try to shift this up it will work because it
            # isn't first in it's set.
            self.get(
                "admin:fixja:reorder",
                "stagegroup",
                pool_b.pk,
                "up",
                extra=dict(HTTP_REFERER="http://testserver/"),
            )
            self.response_302()

            # This time, however, it should fail because we're now first.
            self.get(
                "admin:fixja:reorder",
                "stagegroup",
                pool_b.pk,
                "up",
                extra=dict(HTTP_REFERER="http://testserver/"),
            )
            self.response_404()

    def test_reorder_left(self):
        stage = factories.StageFactory.create()
        pool_a, pool_b, pool_c = factories.StageGroupFactory.create_batch(
            stage=stage, size=3
        )

        with self.login(self.superuser):
            # A direction of "left" is invalid and should throw a 404
            self.get(
                "admin:fixja:reorder",
                pool_b.pk,
                "left",
                extra=dict(HTTP_REFERER="http://testserver/"),
            )
            self.response_404()

    def test_index(self):
        self.assertLoginRequired("admin:fixja:index")
        with self.login(self.superuser):
            self.get("admin:fixja:index")
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

    @unittest.skipIf(
        VERSION > (4, 0), "FIXME: Django 4.1+ error seems to be factory_boy related"
    )
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
        text = """
        <td colspan="5" class="no_results">
            There are no registered players in this team.
        </td>
        """
        self.assertContains(res, text, html=True)

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
        text = """
        <ul class="list-group">
            <li class="list-group-item list-group-item-danger">
                Total number of points (0) does not equal total
                number of scores (3) for this team.
            </li>
        </ul>
        """
        self.assertContains(res, text, html=True)

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

    @unittest.skipIf(
        VERSION > (4, 0), "FIXME: Django 4.1+ error seems to be factory_boy related"
    )
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
        self.post(add_pool.url_name, *add_pool.args, data=data)
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
            "thumbnail_url": "",
        }
        # Unsaved instance means we don't have to trim the final positional argument.
        add_match = Match(stage=stage).url_names["add"]
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
        if VERSION >= (5, 0):
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
        if VERSION >= (5, 0):
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
        if VERSION >= (5, 0):
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
                "thumbnail_url": "",
            }

            # This should complete successfully without TypeError
            self.post(edit_match_url.url_name, *edit_match_url.args, data=data)
            self.response_302()  # Should redirect successfully

            # Verify the match was updated
            match.refresh_from_db()
            self.assertFalse(match.live_stream)
            self.assertIsNone(match.external_identifier)

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
                "thumbnail_url": "",
            }

            # This should complete successfully without TypeError
            self.post(edit_match_url.url_name, *edit_match_url.args, data=data)
            self.response_302()  # Should redirect successfully

            # Verify the match was updated
            match.refresh_from_db()
            self.assertFalse(match.live_stream)
            self.assertIsNone(match.external_identifier)
