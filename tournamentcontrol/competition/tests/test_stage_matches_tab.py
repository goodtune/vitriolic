from test_plus import TestCase

from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests.factories import SuperUserFactory
from tournamentcontrol.competition.tests import factories


@per_shell
class StageMatchesTabQueryTests(TestCase):
    """
    The Matches tab of the stage edit page draws each match with its teams,
    its pool and where it is played, at the same cost however many matches
    the stage has.
    """

    user_factory = SuperUserFactory

    @classmethod
    def _stage(cls, title, matches):
        division = factories.DivisionFactory.create(season=cls.season, title=title)
        stage = factories.StageFactory.create(division=division, order=1)
        pool = factories.StageGroupFactory.create(stage=stage)
        venue = factories.VenueFactory.create(season=cls.season, title=f"{title} Park")
        for number in range(1, matches):
            factories.MatchFactory.create(
                stage=stage,
                stage_group=pool,
                play_at=venue,
                home_team=factories.TeamFactory.create(division=division),
                away_team=factories.TeamFactory.create(division=division),
                label=f"Match {number}",
            )
        factories.MatchFactory.create(
            stage=stage,
            home_team=None,
            away_team=None,
            home_team_undecided=factories.UndecidedTeamFactory.create(
                stage=stage, formula="G1P1", label=""
            ),
            away_team_undecided=factories.UndecidedTeamFactory.create(
                stage=stage, formula="G1P2", label=""
            ),
            label="Playoff",
        )
        return stage

    @classmethod
    def setUpTestData(cls):
        cls.season = factories.SeasonFactory.create()
        cls.few = cls._stage("Few", matches=2)
        cls.many = cls._stage("Many", matches=20)

    def get_stage(self, stage):
        name = "admin:fixja:competition:season:division:stage:edit"
        with self.login(self.make_user()):
            # The current site, the content types guardian asks for and the
            # sitemap's URL patterns are kept for the life of the process.
            # Draw the page once so they are, whichever test runs first.
            self.get_check_200(name, *stage._get_url_args())
            with self.assertNumQueries(self.by_shell(workbook=31, explorer=29)):
                self.get_check_200(name, *stage._get_url_args())

    def test_few_matches(self):
        self.get_stage(self.few)
        self.assertResponseContains(
            self.by_shell(
                workbook='<td data-label="Home">G1P1</td>',
                explorer="<td>G1P1</td>",
            )
        )

    def test_many_matches(self):
        self.get_stage(self.many)
        self.assertResponseContains(
            self.by_shell(
                workbook='<td data-label="Where">Many Park</td>',
                explorer='<td class="wide-only">Many Park</td>',
            )
        )
