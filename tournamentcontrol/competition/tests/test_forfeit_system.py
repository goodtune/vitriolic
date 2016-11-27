from datetime import date

from django.test import override_settings
from freezegun import freeze_time
from test_plus import TestCase

from tournamentcontrol.competition import models
from tournamentcontrol.competition.tests import factories


@override_settings(ROOT_URLCONF='tournamentcontrol.competition.tests.urls')
class GoodViewTests(TestCase):

    user_factory = factories.UserFactory

    def setUp(self):
        # For some reason, using the self.login() context manager with passing
        # a user is not authenticating. TODO fix and create pull request
        # self.user_factory = test_factory.get_user_factory()
        self.person = factories.PersonFactory.create()
        self.user = self.person.user
        self.match = factories.MatchFactory.create()

    def test_forfeit_list(self):
        with self.login(self.user):
            self.assertGoodView(
                'competition:forfeit-list',
                self.match.stage.division.season.competition.slug,
                self.match.stage.division.season.slug)

    def test_forfeit_in_home_team(self):
        self.match.home_team.people.create(
            team=self.match.home_team, person=self.user.person)
        with self.login(self.user):
            self.assertGoodView(
                'competition:forfeit',
                self.match.stage.division.season.competition.slug,
                self.match.stage.division.season.slug,
                self.match.pk)

    def test_forfeit_in_away_team(self):
        self.match.away_team.people.create(
            team=self.match.home_team, person=self.user.person)
        with self.login(self.user):
            self.assertGoodView(
                'competition:forfeit',
                self.match.stage.division.season.competition.slug,
                self.match.stage.division.season.slug,
                self.match.pk)

    def test_forfeit_plays_in_both_teams(self):
        self.match.home_team.people.create(
            team=self.match.home_team, person=self.user.person)
        self.match.away_team.people.create(
            team=self.match.home_team, person=self.user.person)
        with self.login(self.user):
            self.get('competition:forfeit',
                     self.match.stage.division.season.competition.slug,
                     self.match.stage.division.season.slug,
                     self.match.pk)
            self.response_302()

    def test_forfeit_not_in_matches(self):
        match = factories.MatchFactory.create()
        with self.login(self.user):
            self.get('competition:forfeit',
                     match.stage.division.season.competition.slug,
                     match.stage.division.season.slug,
                     match.pk)
            self.response_302()

    @freeze_time("2015-08-18")
    def test_forfeit_match_in_past(self):
        match = factories.MatchFactory.create(date=date(2016, 1, 1))
        match.home_team.people.create(
            team=self.match.home_team, person=self.user.person)
        with self.login(self.user):
            self.assertGoodView(
                'competition:forfeit',
                match.stage.division.season.competition.slug,
                match.stage.division.season.slug,
                match.pk)

    def test_forfeit_post_home_team(self):
        self.match.home_team.people.create(
            team=self.match.home_team, person=self.user.person)
        with self.login(self.user):
            self.post('competition:forfeit',
                      self.match.stage.division.season.competition.slug,
                      self.match.stage.division.season.slug,
                      self.match.pk)
            self.response_302()

        # check the state in the database
        match = models.Match.objects.get(pk=self.match.pk)

        # match should be a forfeit
        self.assertTrue(match.is_forfeit)

        # score should be as per the season rules
        self.assertEqual(match.away_team_score,
                         self.match.stage.division.forfeit_for_score)
        self.assertEqual(match.home_team_score,
                         self.match.stage.division.forfeit_against_score)

    def test_forfeit_post_away_team(self):
        self.match.away_team.people.create(
            team=self.match.home_team, person=self.user.person)
        with self.login(self.user):
            self.post('competition:forfeit',
                      self.match.stage.division.season.competition.slug,
                      self.match.stage.division.season.slug,
                      self.match.pk)
            self.response_302()

        # check the state in the database
        match = models.Match.objects.get(pk=self.match.pk)

        # match should be a forfeit
        self.assertTrue(match.is_forfeit)

        # score should be as per the season rules
        self.assertEqual(match.away_team_score,
                         self.match.stage.division.forfeit_against_score)
        self.assertEqual(match.home_team_score,
                         self.match.stage.division.forfeit_for_score)


@override_settings(ROOT_URLCONF='tournamentcontrol.competition.tests.urls')
class BadViewTests(TestCase):
    """
    Attempt to request views that require an authenticated user.

    They should reliably redirect, we are checking that they do.
    """
    def setUp(self):
        self.match = factories.MatchFactory.create()
        self.user = self.make_user()

    def test_forfeit_list(self):
        self.assertLoginRequired(
            'competition:forfeit-list',
            self.match.stage.division.season.competition.slug,
            self.match.stage.division.season.slug)

    def test_forfeit(self):
        self.assertLoginRequired(
            'competition:forfeit',
            self.match.stage.division.season.competition.slug,
            self.match.stage.division.season.slug,
            self.match.pk)

    def test_forfeit_list_no_person(self):
        with self.login(self.user):
            self.get('competition:forfeit-list',
                     self.match.stage.division.season.competition.slug,
                     self.match.stage.division.season.slug)
            self.response_404()

    def test_forfeit_no_person(self):
        with self.login(self.user):
            self.get('competition:forfeit',
                     self.match.stage.division.season.competition.slug,
                     self.match.stage.division.season.slug,
                     self.match.pk)
            self.response_404()
