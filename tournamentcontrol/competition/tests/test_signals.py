from django.test import TestCase

from tournamentcontrol.competition.models import LadderEntry, LadderSummary
from tournamentcontrol.competition.tests import factories


class SignalHandlerTests(TestCase):
    def test_ladder_entry_match_no_score(self):
        factories.MatchFactory.create()
        self.assertQuerysetEqual(LadderEntry.objects.all(), LadderEntry.objects.none())

    def test_ladder_entry_match_with_score(self):
        factories.MatchFactory.create(home_team_score=5, away_team_score=2)
        self.assertCountEqual(
            [
                (1, 0, 0, 5, 2, 3, 3),
                (0, 1, 0, 2, 5, -3, 3),
            ],
            LadderEntry.objects.values_list(
                "win", "loss", "draw", "score_for", "score_against", "diff", "margin"
            ),
        )

    def test_ladder_summary_3_match_series(self):
        # seed a match which will produce all required relations
        match = factories.MatchFactory.create(home_team_score=5, away_team_score=2)

        # build two more matches with known results to produce LadderSummary
        factories.MatchFactory.create(
            home_team=match.home_team,
            home_team_score=3,
            away_team=match.away_team,
            away_team_score=4,
            stage=match.stage,
        )
        factories.MatchFactory.create(
            home_team=match.home_team,
            home_team_score=2,
            away_team=match.away_team,
            away_team_score=2,
            stage=match.stage,
        )

        self.assertCountEqual(
            [
                (3, 1, 1, 1, 10, 8, 2),
                (3, 1, 1, 1, 8, 10, -2),
            ],
            LadderSummary.objects.values_list(
                "played",
                "win",
                "loss",
                "draw",
                "score_for",
                "score_against",
                "difference",
            ),
        )
