from test_plus import TestCase

from touchtechnology.admin.tests.links import LinksMixin
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests.factories import UserFactory
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
    """
    Deleting a season or a score sheet, or saving a team's permissions, ends on
    a page.
    """

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

    def test_deleting_a_score_sheet_returns_to_the_match(self):
        # A match's score sheets have no list of their own: they are a tab of
        # the match's page.
        match = factories.MatchFactory.create()
        scoresheet = MatchScoreSheet.objects.create(
            match=match, image="harness/score-sheet"
        )
        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:division:stage:match:"
                "matchscoresheet:delete",
                *scoresheet._get_url_args(),
            )
            self.assert_http_302_found(url=f"{match.urls['edit']}#scoresheets-tab")
            self.get_check_200(
                "admin:fixja:competition:season:division:stage:match:edit",
                *match._get_url_args(),
            )
        self.assertCountEqual(match.scoresheets.all(), [])

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
