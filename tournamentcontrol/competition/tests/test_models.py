from test_plus import TestCase

from tournamentcontrol.competition.models import Match, Season

NOOP = lambda o: o


class MatchEvalTest(TestCase):
    """
    Need to construct test cases where we can validate the behaviour of
    the Match.eval method.
    """

    fixtures = ['club', 'person', 'competition', 'season', 'place',
                'division', 'stage', 'team', 'match']

    def test_first_stage(self):
        "Match in first stage will never evaluate - return actual teams."
        match = Match.objects.get(pk=1)
        home_team, away_team = match.eval()
        self.assertEqual(home_team, match.home_team)
        self.assertEqual(away_team, match.away_team)

    def test_follow_normal_stage(self):  # TODO
        "No pools in previous stage - straight positional map."

    def test_follow_pool_stage(self):  # TODO
        "Pool based previous stage - find in dictionary mapping."

    def test_undecided_team_following_normal_stage(self):  # TODO
        "Using undecided teams after a normal stage."

    def test_undecided_team_following_pool_stage(self):  # TODO
        "Using undecided teams after a pool stage."


class MatchTest(TestCase):

    fixtures = ['club', 'person', 'competition', 'season', 'place',
                'division', 'stage', 'team', 'match']

    def test_match_multiple_videos(self):
        self.assertQuerysetEqual(
            Match.objects.filter(pk=1),
            Season.objects.get(pk=1).matches.videos(),
            transform=NOOP)
