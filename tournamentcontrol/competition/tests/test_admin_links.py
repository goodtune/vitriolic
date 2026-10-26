from test_plus import TestCase

from touchtechnology.admin.tests.links import LinksMixin
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests.factories import StaffFactory, UserFactory
from tournamentcontrol.competition.models import MatchScoreSheet
from tournamentcontrol.competition.tests import factories


@per_shell
class CompetitionLinksTests(LinksMixin, TestCase):
    """Every link on the competition pages leads to a page that answers."""

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.team = factories.TeamFactory.create()
        self.division = self.team.division
        self.season = self.division.season
        self.competition = self.season.competition

    def test_the_trail_and_sections_of_a_season(self):
        with self.login(self.superuser):
            self.follow_links(
                "admin:fixja:competition:season:edit",
                self.competition.pk,
                self.season.pk,
                selector="nav a",
            )

    def test_the_trail_and_sections_of_a_division(self):
        with self.login(self.superuser):
            self.follow_links(
                "admin:fixja:competition:season:division:edit",
                self.competition.pk,
                self.season.pk,
                self.division.pk,
                selector="nav a",
            )

    def test_the_trail_and_sections_of_a_team(self):
        with self.login(self.superuser):
            self.follow_links(
                "admin:fixja:competition:season:division:team:edit",
                self.competition.pk,
                self.season.pk,
                self.division.pk,
                self.team.pk,
                selector="nav a",
            )

    def test_every_link_of_a_division_moves_nothing(self):
        """
        Following every link of a division's page leaves its stages and teams
        in their order: the arrows that move them are forms that post.
        """
        stages = [
            factories.StageFactory.create(division=self.division, order=n)
            for n in (1, 2)
        ]
        teams = [
            self.team,
            factories.TeamFactory.create(
                division=self.division, order=self.team.order + 1
            ),
        ]
        with self.login(self.superuser):
            self.follow_links(
                "admin:fixja:competition:season:division:edit",
                self.competition.pk,
                self.season.pk,
                self.division.pk,
            )
        self.assertEqual(list(self.division.stages.all()), stages)
        self.assertEqual(list(self.division.teams.all()), teams)

    def test_the_permissions_of_a_competition(self):
        with self.login(self.superuser):
            self.follow_links("admin:fixja:competition:perms", self.competition.pk)

    def test_the_permissions_of_a_season(self):
        with self.login(self.superuser):
            self.follow_links(
                "admin:fixja:competition:season:perms",
                self.competition.pk,
                self.season.pk,
            )

    def test_the_permissions_of_a_team(self):
        with self.login(self.superuser):
            self.follow_links(
                "admin:fixja:competition:season:division:team:perms",
                self.competition.pk,
                self.season.pk,
                self.division.pk,
                self.team.pk,
            )


class CompetitionRedirectsTests(TestCase):
    """Deleting a season, or saving a team's permissions, ends on a page."""

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def test_deleting_a_season_returns_to_the_competition(self):
        season = factories.SeasonFactory.create()
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:delete",
                season.competition_id,
                season.pk,
            )
        self.assert_http_302_found(url=f"{season.competition.urls['edit']}#seasons-tab")

    def test_saving_the_permissions_of_a_team_returns_to_the_division(self):
        team = factories.TeamFactory.create()
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:division:team:perms",
                team.division.season.competition_id,
                team.division.season_id,
                team.division_id,
                team.pk,
                data={"form-TOTAL_FORMS": 0, "form-INITIAL_FORMS": 0},
            )
        self.assert_http_302_found(url=f"{team.division.urls['edit']}#teams-tab")


class ScoreSheetDeleteTests(TestCase):
    """
    A match's score sheets have no list of their own: they are a tab of the
    match's page, so deleting one returns there.
    """

    user_factory = StaffFactory

    @classmethod
    def setUpTestData(cls):
        cls.match = factories.MatchFactory.create()
        cls.scoresheet = MatchScoreSheet.objects.create(
            match=cls.match, image="harness/score-sheet"
        )
        cls.deleter = cls.make_user(
            "deleter",
            perms=["competition.delete_matchscoresheet", "competition.change_match"],
        )
        cls.editor = cls.make_user("editor", perms=["competition.change_match"])

    def delete_scoresheet(self, match):
        """Post the delete of the score sheet through the address of ``match``."""
        self.post(
            "admin:fixja:competition:season:division:stage:match:"
            "matchscoresheet:delete",
            *match._get_url_args(),
            self.scoresheet.pk,
        )

    def test_deleting_returns_to_the_match(self):
        with self.login(self.deleter):
            self.delete_scoresheet(self.match)
            self.assert_http_302_found(url=f"{self.match.urls['edit']}#scoresheets-tab")
            self.get_check_200(
                "admin:fixja:competition:season:division:stage:match:edit",
                *self.match._get_url_args(),
            )
        self.assertCountEqual(self.match.scoresheets.all(), [])

    def test_deleting_through_another_match_is_not_found(self):
        other = factories.MatchFactory.create(stage=self.match.stage)
        with self.login(self.deleter):
            self.delete_scoresheet(other)
        self.assert_http_404_not_found()
        self.assertEqual(self.match.scoresheets.count(), 1)

    def test_deleting_needs_the_permission(self):
        with self.login(self.editor):
            self.delete_scoresheet(self.match)
        self.assert_http_403_forbidden()
        self.assertCountEqual(self.match.scoresheets.all(), [self.scoresheet])
