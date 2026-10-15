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

    def test_mysideline_match_is_not_editable(self):
        mirrored = self.match(mysideline_id=42)
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
        self.match(mysideline_id=42)
        self.match(home_team_score=1, away_team_score=0)
        with self.assertNumQueries(1):
            states = [
                (m.has_result, m.result_editable)
                for m in Match.objects.with_result_state().order_by("pk")
            ]
        self.assertEqual(states, [(False, False), (False, False), (True, True)])
