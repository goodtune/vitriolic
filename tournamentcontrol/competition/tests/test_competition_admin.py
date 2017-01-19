import unittest

from datetime import time

import django

from django.conf import settings
from django.core.urlresolvers import reverse
from django.test.utils import override_settings
from test_plus import TestCase as BaseTestCase
from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.models import (
    Club,
    Division,
    Match,
    Season,
    StageGroup,
    Team,
    UndecidedTeam,
)
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.utils import round_robin


class TestCase(BaseTestCase):

    def setUp(self):
        super(TestCase, self).setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def assertGoodEditView(self, viewname, *args, **kwargs):
        test_query_count = kwargs.pop('test_query_count', 50)
        self.assertLoginRequired(viewname, *args)
        with self.login(self.superuser):
            self.assertGoodView(
                viewname, test_query_count=test_query_count, *args)
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
        self.assertGoodEditView('%s:add' % namespace, *args[:-1], **kwargs)
        self.assertGoodEditView('%s:edit' % namespace, *args, **kwargs)
        self.assertGoodDeleteView('%s:delete' % namespace, *args)


class GoodViewTests(TestCase):

    def test_reorder_down(self):
        stage = factories.StageFactory.create()
        pool_a, pool_b, pool_c = \
            factories.StageGroupFactory.create_batch(stage=stage, size=3)

        with self.login(self.superuser):
            # Without a HTTP_REFERER set this should throw a 404
            self.get('admin:fixja:reorder', 'stagegroup', pool_b.pk, 'down')
            self.response_404()

            # The first time we try to shift this down it will work because it
            # isn't last in it's set.
            self.get('admin:fixja:reorder', 'stagegroup', pool_b.pk, 'down',
                     extra=dict(HTTP_REFERER='http://testserver/'))
            self.response_302()

            # This time, however, it should fail because we're now last.
            self.get('admin:fixja:reorder', 'stagegroup', pool_b.pk, 'down',
                     extra=dict(HTTP_REFERER='http://testserver/'))
            self.response_404()

    def test_reorder_up(self):
        stage = factories.StageFactory.create()
        pool_a, pool_b, pool_c = \
            factories.StageGroupFactory.create_batch(stage=stage, size=3)

        with self.login(self.superuser):
            # Without a HTTP_REFERER set this should throw a 404
            self.get('admin:fixja:reorder', 'stagegroup', pool_b.pk, 'up')
            self.response_404()

            # The first time we try to shift this up it will work because it
            # isn't first in it's set.
            self.get('admin:fixja:reorder', 'stagegroup', pool_b.pk, 'up',
                     extra=dict(HTTP_REFERER='http://testserver/'))
            self.response_302()

            # This time, however, it should fail because we're now first.
            self.get('admin:fixja:reorder', 'stagegroup', pool_b.pk, 'up',
                     extra=dict(HTTP_REFERER='http://testserver/'))
            self.response_404()

    def test_reorder_left(self):
        stage = factories.StageFactory.create()
        pool_a, pool_b, pool_c = \
            factories.StageGroupFactory.create_batch(stage=stage, size=3)

        with self.login(self.superuser):
            # A direction of "left" is invalid and should throw a 404
            self.get('admin:fixja:reorder', pool_b.pk, 'left',
                     extra=dict(HTTP_REFERER='http://testserver/'))
            self.response_404()

    def test_index(self):
        self.assertLoginRequired('admin:fixja:index')
        with self.login(self.superuser):
            self.get('admin:fixja:index')
            self.response_302()

    def test_competition(self):
        competition = factories.CompetitionFactory.create()
        self.assertLoginRequired('admin:fixja:competition:list')
        with self.login(self.superuser):
            self.assertGoodView('admin:fixja:competition:list')
        self.assertGoodNamespace(competition)

    def test_clubrole(self):
        role = factories.ClubRoleFactory.create()
        self.assertGoodNamespace(role, data={'name': 'Club Role'})

    def test_teamrole(self):
        role = factories.TeamRoleFactory.create()
        self.assertGoodNamespace(role, data={'name': 'Team Role'})

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

    def test_matchvideo(self):
        video = factories.MatchVideoFactory.create()
        self.assertGoodNamespace(video)

    def test_pool(self):
        pool = factories.StageGroupFactory.create()
        self.assertGoodNamespace(pool)

    @unittest.skip("Should not be, but is, failing.")
    def test_club(self):
        club = factories.ClubFactory.create()
        self.assertLoginRequired('admin:fixja:club:list')
        with self.login(self.superuser):
            self.assertGoodView('admin:fixja:club:list')
        self.assertGoodNamespace(club)

    def test_person(self):
        person = factories.PersonFactory.create()
        self.assertFalse(person.statistics.count())
        self.assertGoodNamespace(person)

    def test_format(self):
        draw_format = factories.DrawFormatFactory.create()
        self.assertLoginRequired('admin:fixja:format:list')
        with self.login(self.superuser):
            self.assertGoodView('admin:fixja:format:list')
        self.assertGoodNamespace(draw_format)

    @unittest.skip("Not refactored as a namespace yet")
    def test_list_drawformat(self):
        self.assertLoginRequired('admin:fixja:report:list')
        with self.login(self.superuser):
            self.assertGoodView('admin:fixja:report:list')

    # code coverage

    def test_season_report(self):
        season = factories.SeasonFactory.create()
        self.assertLoginRequired(
            'admin:fixja:season-report', season.competition_id, season.pk)
        with self.login(self.superuser):
            self.assertGoodView(
                'admin:fixja:season-report', season.competition_id, season.pk)

    def test_season_summary(self):
        season = factories.SeasonFactory.create()
        self.assertLoginRequired(
            'admin:fixja:season-summary', season.competition_id, season.pk)
        with self.login(self.superuser):
            self.assertGoodView(
                'admin:fixja:season-summary', season.competition_id, season.pk)

    def test_progress_teams(self):
        division = factories.DivisionFactory.create()
        teams = factories.TeamFactory.create_batch(division=division, size=6)

        round_games, finals = factories.StageFactory.create_batch(
            division=division, size=2)

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
            stage=finals, label='Semi 1', round=6,
            home_team=None, home_team_eval='P1',
            away_team=None, away_team_eval='P4')
        semi_2 = factories.MatchFactory.create(
            stage=finals, label='Semi 2', round=6,
            home_team=None, home_team_eval='P2',
            away_team=None, away_team_eval='P3')
        final = factories.MatchFactory.create(
            stage=finals, label='Final', round=7,
            home_team=None, home_team_eval='W', home_team_eval_related=semi_1,
            away_team=None, away_team_eval='W', away_team_eval_related=semi_2)

        self.assertLoginRequired(
            round_games._get_admin_namespace() + ':draw:progress',
            *round_games._get_url_args())

        with self.login(self.superuser):
            # The round games cannot be progressed, it's the first stage and
            # therefore can't have any undecided teams.
            self.get(round_games._get_admin_namespace() + ':draw:progress',
                     *round_games._get_url_args())
            self.response_410()

            # FIXME
            #
            # # The final series can't be progressed because there are results
            # # that need to be entered for matches in the preceding stage.
            # self.get(finals._get_admin_namespace() + ':draw:progress',
            #          *finals._get_url_args())
            # self.response_410()
            #
            # # Set random results for every unplayed match in the previous stage
            # # so that we can determine progressions.
            # for m in round_games.matches.all():
            #     m.home_team_score = random.randint(0, 20)
            #     m.away_team_score = random.randint(0, 20)

            # The final series progression should now be accessible.
            self.get(finals._get_admin_namespace() + ':draw:progress',
                     *finals._get_url_args())
            self.response_200()

    def test_edit_person(self):
        person = factories.PersonFactory.create()
        self.assertLoginRequired(
            'admin:fixja:club:person:add',
            person.club.pk)
        self.assertLoginRequired(
            'admin:fixja:club:person:edit',
            person.club.pk,
            person.pk)
        with self.login(self.superuser):
            self.assertGoodView(
                'admin:fixja:club:person:add',
                person.club.pk)
            self.assertGoodView(
                'admin:fixja:club:person:edit',
                person.club.pk,
                person.pk)

    def test_edit_clubassociation(self):
        association = factories.ClubAssociationFactory.create()
        self.assertLoginRequired(
            'admin:fixja:club:clubassociation:add',
            association.club.pk)
        self.assertLoginRequired(
            'admin:fixja:club:clubassociation:edit',
            association.club.pk,
            association.pk)
        with self.login(self.superuser):
            self.assertGoodView(
                'admin:fixja:club:clubassociation:add',
                association.club.pk)
            self.assertGoodView(
                'admin:fixja:club:clubassociation:edit',
                association.club.pk,
                association.pk)

    # def test_delete_competition(self):
    #     self.assertLoginRequired('admin:fixja:competition:delete', 1)
    #     with self.login(username='gary@touch.asn.au'):
    #         self.get('admin:fixja:competition:delete', 1)
    #         self.response_405()
    #         self.post('admin:fixja:competition:delete', 1)
    #         self.response_302()

    def test_perms_views(self):
        team = factories.TeamFactory.create()
        self.assertLoginRequired(
            team.division.season.competition._get_admin_namespace() + ':perms',
            *team._get_url_args()[:1])
        self.assertLoginRequired(
            team.division.season._get_admin_namespace() + ':perms',
            *team._get_url_args()[:2])
        # self.assertLoginRequired(
        #     team.division._get_admin_namespace() + ':perms',
        #     *team._get_url_args()[:3])
        self.assertLoginRequired(
            team._get_admin_namespace() + ':perms',
            *team._get_url_args())

        with self.login(self.superuser):
            self.assertGoodView(
                team.division.season.competition._get_admin_namespace() + ':perms',
                *team._get_url_args()[:1])
            self.assertGoodView(
                team.division.season._get_admin_namespace() + ':perms',
                *team._get_url_args()[:2])
            # self.assertGoodView(
            #     team.division._get_admin_namespace() + ':perms',
            #     *team._get_url_args()[:3])
            with self.assertNumQueriesLessThan(100):
                self.get(
                    team._get_admin_namespace() + ':perms',
                    *team._get_url_args())
            self.response_200()

    def test_registration_form(self):
        club = factories.ClubFactory.create()
        team = factories.TeamFactory.create(club=club)
        team.division.season.competition.clubs.add(club)
        self.assertLoginRequired('admin:fixja:club:registration-form',
                                 club.pk, team.division.season.pk, 'html')
        with self.login(self.superuser):
            self.assertGoodView('admin:fixja:club:registration-form',
                                club.pk, team.division.season.pk, 'html')

    @unittest.expectedFailure
    def test_edit_team_members(self):
        club = factories.ClubFactory.create()
        team = factories.TeamFactory.create(club=club)
        self.assertLoginRequired('admin:fixja:club:team:edit',
                                 club.pk, team.division.season.pk, team.pk)
        with self.login(self.superuser):
            self.assertGoodView('admin:fixja:club:team:edit',
                                club.pk, team.division.season.pk, team.pk)


class BackendTests(TestCase):

    def setUp(self):
        super(BackendTests, self).setUp()
        self.login(self.superuser)

    @unittest.skipIf(
        django.VERSION > (1, 8) and
        settings.DATABASES['default']['ENGINE'].endswith('psycopg2'),
        "Django 1.9+ & PostgreSQL errors with 'GROUP BY' on annotate")
    def test_task_0058_highest_point_scorer(self):
        division = factories.DivisionFactory.create()
        self.assertGoodView(
            division._get_admin_namespace() + ':scorers',
            *division._get_url_args())

    def test_add_division(self):
        """
        Using the admin interface, add a new division and check that it appears
        in the front-end. Later update the form data and repost to ensure the
        front-end is also updated.
        """
        season = factories.SeasonFactory.create()
        data = {
            'title': 'Mixed 4',
            'short_title': 'X4',
            'points_formula_0': '3',
            'points_formula_1': '2',
            'points_formula_2': '1',
            'points_formula_3': '',
            'points_formula_4': '',
            'points_formula_5': '',
            'forfeit_for_score': '5',
            'forfeit_against_score': '0',
            'include_forfeits_in_played': '1',
            'slug': '',
            'slug_locked': '0',
        }
        self.post(season._get_admin_namespace() + ':division:add',
                  *season._get_url_args(), data=data)
        self.response_302()

        with self.settings(
                ROOT_URLCONF='tournamentcontrol.competition.tests.urls'):
            self.assertGoodView('competition:season',
                                season.competition.slug, season.slug)
            self.assertResponseContains('Mixed 4', html=False)
            self.assertGoodView('competition:division',
                                season.competition.slug,
                                season.slug, 'mixed-4')
            self.assertResponseContains('Mixed 4', html=False)

        data.update({
            'title': '4th Division Mixed',
        })
        division = season.divisions.latest('pk')

        self.post(division._get_admin_namespace() + ':edit',
                  *division._get_url_args(), data=data)
        self.response_302()

        with self.settings(
                ROOT_URLCONF='tournamentcontrol.competition.tests.urls'):
            self.assertGoodView('competition:season',
                                season.competition.slug, season.slug)
            self.assertResponseNotContains('Mixed 4', html=False)
            self.assertResponseContains('4th Division Mixed', html=False)

    def test_update_club(self):
        """
        Using the admin interface, update an existing Club and ensure that the
        revised attribute is correctly updated.
        """
        club = factories.ClubFactory.create()
        data = {
            'title': 'Bare Back Riders',
            'short_title': '',
            'abbreviation': 'BBR',
            'website': '',
            'twitter': '',
            'primary': '',
            'slug': 'bare-back-riders',
            'slug_locked': '0',
        }
        self.post('admin:fixja:club:edit', club.pk, data=data)
        self.response_302()

        self.get('admin:fixja:club:list')
        self.assertResponseContains('Bare Back Riders', html=False)
        self.assertResponseContains('BBR', html=False)

    @unittest.skip('Not in the fixja namespace.')
    def test_match_detail(self):
        # Add scoreline to match or this will be a 404
        Match.objects.filter(pk=1).update(home_team_score=3,
                                          away_team_score=0)
        m = Match.objects.get(pk=1)

        kwargs = {
            'match_id': m.pk,
            'stage_id': m.stage_id,
            'division_id': m.stage.division_id,
            'season_id': m.stage.division.season_id,
            'competition_id': m.stage.division.season.competition_id,
        }
        url = reverse(
            'admin:competition:competition:season:division:stage:match:detail',
            kwargs=kwargs)

        res = self.client.get(url)

        # After GET ensure away_team has no players
        text = '''
        <td colspan="5" class="no_results">
            There are no registered players in this team.
        </td>
        '''
        self.assertContains(res, text, html=True)

        data = {
            'home-0-number': '3',
            'home-0-id': '',
            'home-0-played': '1',
            'home-0-points': '0',
            'home-0-mvp': '0',

            'home-1-number': '8',
            'home-1-id': '',
            'home-1-played': '1',
            'home-1-points': '0',
            'home-1-mvp': '0',

            'home-2-number': '10',
            'home-2-id': '',
            'home-2-played': '1',
            'home-2-points': '0',
            'home-2-mvp': '0',

            'home-3-number': '12',
            'home-3-id': '',
            'home-3-played': '1',
            'home-3-points': '0',
            'home-3-mvp': '0',

            'home-TOTAL_FORMS': '4',
            'home-INITIAL_FORMS': '4',
            'home-MAX_NUM_FORMS': '1000',

            'away-TOTAL_FORMS': '0',
            'away-INITIAL_FORMS': '0',
            'away-MAX_NUM_FORMS': '1000',
        }

        res = self.client.post(url, data=data)
        text = '''
        <ul class="list-group">
            <li class="list-group-item list-group-item-danger">
                Total number of points (0) does not equal total
                number of scores (3) for this team.
            </li>
        </ul>
        '''
        self.assertContains(res, text, html=True)

        data.update({
            'home-0-points': '0',
            'home-1-points': '1',
            'home-2-points': '0',
            'home-3-points': '2',
        })
        res = self.client.post(url, data=data)
        self.assertRedirects(res, reverse('admin:index'))

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

        self.post('admin:fixja:match-results',
                  match.stage.division.season.competition.pk,
                  match.stage.division.season.pk,
                  match.date.strftime('%Y%m%d'),
                  data=data)
        self.response_302()

        data.update({
            "matches-1-home_team_score": "5",
            "matches-1-away_team_score": "2",
        })
        self.post('admin:fixja:match-results',
                  match.stage.division.season.competition.pk,
                  match.stage.division.season.pk,
                  match.date.strftime('%Y%m%d'),
                  data=data)
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
            stage=stage,
            home_team=home,
            away_team=None, away_team_undecided=away)

        delete_url = self.reverse(
            home._get_admin_namespace() + ':delete', *home._get_url_args())

        # Ensure the edit view response does not include a delete button.
        self.get(home._get_admin_namespace() + ':edit', *home._get_url_args())
        self.assertResponseNotContains(delete_url, html=False)

        # Ensure that visiting the delete view does not respond when matches
        # are associated with the Team.
        self.get(
            home._get_admin_namespace() + ':delete', *home._get_url_args())
        self.response_410()

        # Ensure that POST to the delete view fails the same as for GET.
        self.post(
            home._get_admin_namespace() + ':delete', *home._get_url_args())
        self.response_410()

        # Create a new Team and re-check the scenarios.
        team = factories.TeamFactory.create(division=stage.division)

        delete_url = self.reverse(
            team._get_admin_namespace() + ':delete', *team._get_url_args())

        # Ensure the edit view response does not include a delete button.
        self.get(team._get_admin_namespace() + ':edit', *team._get_url_args())
        self.assertResponseNotContains(delete_url, html=False)

        # Ensure that visiting the delete view is not allowed when there are no
        # matches but you use a GET request.
        self.get(
            team._get_admin_namespace() + ':delete', *team._get_url_args())
        self.response_405()

        # Ensure that POST to the delete view redirects.
        self.post(
            team._get_admin_namespace() + ':delete', *team._get_url_args())
        self.response_302()

        # Subsequent GET request to the edit view should be a 404.
        self.get(
            team._get_admin_namespace() + ':edit', *team._get_url_args())
        self.response_404()

    def test_enhancement_0024_undecidedteam(self):
        """
        When editing a Team or UndecidedTeam it should be possible to delete
        the object if there are no matches that team has been assigned to.
        """
        stage = factories.StageFactory.create()
        home = factories.TeamFactory.create(division=stage.division)
        away = factories.UndecidedTeamFactory.create(stage=stage)

        factories.MatchFactory.create(stage=stage,
                                      home_team=home,
                                      away_team=None,
                                      away_team_undecided=away)

        delete_url = self.reverse(away._get_admin_namespace() + ':delete',
                                  *away._get_url_args())

        # Ensure the edit view response does not include a delete button.
        self.get(away._get_admin_namespace() + ':edit', *away._get_url_args())
        self.assertResponseNotContains(delete_url, html=False)

        # Ensure that visiting the delete view does not respond when matches
        # are associated with the Team.
        self.get(away._get_admin_namespace() + ':delete',
                 *away._get_url_args())
        self.response_410()

        # Ensure that POST to the delete view fails the same as for GET.
        self.post(away._get_admin_namespace() + ':delete',
                  *away._get_url_args())
        self.response_410()

        # Create a new UndecidedTeam and re-check the scenarios.
        team = factories.UndecidedTeamFactory.create(stage=stage)

        delete_url = self.reverse(team._get_admin_namespace() + ':delete',
                                  *team._get_url_args())

        # Ensure the edit view response *does* include a delete button.
        self.get(stage._get_admin_namespace() + ':edit',
                 *stage._get_url_args())
        self.assertResponseContains(delete_url, html=False)

        # Ensure that visiting the delete view is not allowed when there are no
        # matches but you use a GET request.
        self.get(team._get_admin_namespace() + ':delete',
                 *team._get_url_args())
        self.response_405()

        # Ensure that POST to the delete view redirects.
        self.post(team._get_admin_namespace() + ':delete',
                  *team._get_url_args())
        self.response_302()

        # Subsequent GET request to the edit view should be a 404.
        self.get(team._get_admin_namespace() + ':delete',
                 *team._get_url_args())
        self.response_404()

    def test_bug_80_add_stagegroup(self):
        "Add Pool should gain order equal to max(order) + 1"
        pool = factories.StageGroupFactory.create()
        data = {
            'title': 'Group Z',
            'short_title': '',
            'slug': '',
            'slug_locked': '0',
            'carry_ladder': '0',
        }
        self.post(pool._get_admin_namespace() + ':add',
                  *pool._get_url_args()[:-1], data=data)
        self.response_302()
        z = pool.stage.pools.latest('order')
        self.assertEqual(z.order, pool.order + 1)

    def test_bug_0115_add_duplicate_team_name(self):
        """
        When adding two teams to the same division, it should not allow the
        second one because of database integrity constraints.
        """
        team = factories.TeamFactory.create()
        data = {
            'title': team.title,
        }
        # print self.reverse(team._get_admin_namespace() + ':add',
        #                    *team._get_url_args()[:-1])
        self.post(team._get_admin_namespace() + ':add',
                  *team._get_url_args()[:-1], data=data)
        self.assertResponseContains(
            "Team name must be unique in this division.", html=False)

    def test_team_add(self):
        division = factories.DivisionFactory.create()
        data = {
            'title': 'New Team',  # current value
            'short_title': '',
            'names_locked': '0',
            'timeslots_after_0': '',
            'timeslots_after_1': '',
            'timeslots_before_0': '',
            'timeslots_before_1': '',
            'team_clashes': [],
        }
        self.post(division._get_admin_namespace() + ':team:add',
                  *division._get_url_args(), data=data)
        self.response_302()
        # Ensure that the team was created and that it has a slug
        team = Team.objects.get(title='New Team')
        self.assertEqual(team.slug, 'new-team')

    def test_team_edit(self):
        team = factories.TeamFactory.create()
        data = {
            'title': 'Blue',
            'short_title': '',
            'names_locked': '0',
            'timeslots_after_0': '19',  # new value
            'timeslots_after_1': '20',  # new value
            'timeslots_before_0': '',
            'timeslots_before_1': '',
            'team_clashes': [],
        }

        self.post(team._get_admin_namespace() + ':edit',
                  *team._get_url_args(), data=data)
        self.response_302()

        # Ensure that the team was updated
        blue = Team.objects.get(title='Blue')
        self.assertEqual(team.pk, blue.pk)
        self.assertEqual(blue.slug, 'blue')
        self.assertEqual(blue.timeslots_after, time(19, 20))

        # Try again, update the title and make sure the slug changes
        data['title'] = 'Magenta'
        self.post(blue._get_admin_namespace() + ':edit',
                  *blue._get_url_args(), data=data)
        self.response_302()

        magenta = Team.objects.get(title='Magenta')
        self.assertEqual(team.pk, magenta.pk)
        self.assertEqual(magenta.slug, 'magenta')
        self.assertEqual(magenta.timeslots_after, time(19, 20))
