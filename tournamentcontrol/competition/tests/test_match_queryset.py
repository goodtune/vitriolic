from test_plus import TestCase

from tournamentcontrol.competition.models import Match
from tournamentcontrol.competition.tests import factories


class WithResultStateTests(TestCase):
    def setUp(self):
        self.stage = factories.StageFactory.create()

    def match(self, **kwargs):
        return factories.MatchFactory.create(stage=self.stage, **kwargs)

    def state(self, match):
        annotated = Match.objects.with_result_state().get(pk=match.pk)
        return (
            annotated.has_result,
            annotated.needs_progressing,
            annotated.result_editable,
        )

    def test_processed_bye_has_a_result(self):
        bye = self.match(is_bye=True, away_team=None, bye_processed=True)
        self.assertEqual(self.state(bye), (True, False, True))

    def test_unprocessed_bye_has_no_result(self):
        bye = self.match(is_bye=True, away_team=None)
        self.assertEqual(self.state(bye), (False, False, True))

    def test_both_scores_are_a_result(self):
        scored = self.match(home_team_score=3, away_team_score=1)
        self.assertEqual(self.state(scored), (True, False, True))

    def test_one_score_is_not_a_result(self):
        half = self.match(home_team_score=3)
        self.assertEqual(self.state(half), (False, False, True))

    def test_forfeit_is_a_result(self):
        forfeit = self.match(is_forfeit=True)
        self.assertEqual(self.state(forfeit), (True, False, True))

    def test_washout_is_a_result(self):
        washout = self.match(is_washout=True)
        self.assertEqual(self.state(washout), (True, False, True))

    def test_upstream_match_is_not_editable(self):
        mirrored = self.match(upstream_id="mysideline:42")
        self.assertEqual(self.state(mirrored), (False, False, False))

    def test_match_awaiting_progression_is_not_editable(self):
        undecided = factories.UndecidedTeamFactory.create(stage=self.stage)
        pending = self.match(home_team=None, home_team_undecided=undecided)
        self.assertEqual(self.state(pending), (False, True, False))

    def test_match_of_a_complete_season_needs_no_progressing(self):
        season = self.stage.division.season
        season.complete = True
        season.save()
        undecided = factories.UndecidedTeamFactory.create(stage=self.stage)
        pending = self.match(home_team=None, home_team_undecided=undecided)
        self.assertEqual(self.state(pending), (False, False, True))

    def test_state_costs_one_query(self):
        undecided = factories.UndecidedTeamFactory.create(stage=self.stage)
        self.match(home_team=None, home_team_undecided=undecided)
        self.match(upstream_id="mysideline:42")
        self.match(home_team_score=1, away_team_score=0)
        with self.assertNumQueries(1):
            states = [
                (m.has_result, m.result_editable)
                for m in Match.objects.with_result_state().order_by("pk")
            ]
        self.assertEqual(states, [(False, False), (False, False), (True, True)])


class ByeTitleTests(TestCase):
    """
    A bye is named in plain text, by the model and by the database, so that the
    name can go anywhere text goes: an attribute, a page title, a feed.
    """

    def setUp(self):
        self.stage = factories.StageFactory.create()

    def test_a_bye_at_home_is_named_in_plain_text(self):
        bye = factories.MatchFactory.create(
            stage=self.stage, is_bye=True, home_team=None, away_team__title="Marlins"
        )
        self.assertEqual(
            (str(bye), str(bye.get_home_team_plain()), str(bye.get_away_team_plain())),
            ("Bye vs Marlins", "Bye", "Marlins"),
        )

    def test_a_bye_away_is_named_in_plain_text(self):
        bye = factories.MatchFactory.create(
            stage=self.stage, is_bye=True, home_team__title="Leopards", away_team=None
        )
        self.assertEqual(
            (str(bye), str(bye.get_home_team_plain()), str(bye.get_away_team_plain())),
            ("Leopards vs Bye", "Leopards", "Bye"),
        )

    def test_the_side_with_the_bye_is_false(self):
        """
        A bye is false and a team is true, so ``away or home`` (and the
        ``default`` filter) gives the team of a bye on either side.
        """
        bye = factories.MatchFactory.create(
            stage=self.stage, is_bye=True, home_team=None, away_team__title="Marlins"
        )
        self.assertEqual(
            [
                bool(team)
                for team in (
                    bye.get_home_team(),
                    bye.get_home_team_plain(),
                    bye.get_away_team(),
                    bye.get_away_team_plain(),
                )
            ],
            [False, False, True, True],
        )

    def test_the_database_names_a_bye_in_plain_text(self):
        bye = factories.MatchFactory.create(
            stage=self.stage, is_bye=True, home_team__title="Leopards", away_team=None
        )
        self.assertEqual(
            Match.objects.filter(pk=bye.pk)
            .values_list("home_team_title", "away_team_title")
            .get(),
            ("Leopards", "Bye"),
        )
