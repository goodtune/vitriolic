from test_plus import TestCase

from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests.caches import WarmCachesMixin
from touchtechnology.common.tests.factories import SuperUserFactory
from tournamentcontrol.competition.tests import factories


@per_shell
class StageMatchesTabQueryTests(WarmCachesMixin, TestCase):
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
            self.warm_caches()
            with self.assertNumQueries(23):
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


@per_shell
class LaterStageMatchesTabQueryTests(WarmCachesMixin, TestCase):
    """
    The Matches tab of a later stage names each team still to be decided by
    its place on the ladder of the stage before, reading the division's
    stages once however many matches name one.
    """

    user_factory = SuperUserFactory

    @classmethod
    def _stage(cls, title, matches):
        division = factories.DivisionFactory.create(season=cls.season, title=title)
        factories.StageFactory.create(division=division, order=1, title="Pool Play")
        stage = factories.StageFactory.create(
            division=division, order=2, title="Finals"
        )
        for number in range(1, matches + 1):
            factories.MatchFactory.create(
                stage=stage,
                home_team=None,
                away_team=None,
                home_team_eval="P1",
                away_team_eval="P2",
                label=f"Final {number}",
            )
        return stage

    @classmethod
    def setUpTestData(cls):
        cls.season = factories.SeasonFactory.create()
        cls.few = cls._stage("Few", matches=1)
        cls.many = cls._stage("Many", matches=10)

    def get_stage(self, stage):
        name = "admin:fixja:competition:season:division:stage:edit"
        with self.login(self.make_user()):
            self.warm_caches()
            with self.assertNumQueries(25):
                self.get_check_200(name, *stage._get_url_args())
        self.assertResponseContains(
            self.by_shell(
                workbook='<td data-label="Home">1st</td>',
                explorer="<td>1st</td>",
            )
        )

    def test_few_matches(self):
        self.get_stage(self.few)

    def test_many_matches(self):
        self.get_stage(self.many)
