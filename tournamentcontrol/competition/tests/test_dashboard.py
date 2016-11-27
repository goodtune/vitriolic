from unittest import skip

from django.core.urlresolvers import reverse
from test_plus import TestCase

from tournamentcontrol.competition.models import Match

@skip("skip while refactoring")
class DashboardTests(TestCase):

    fixtures = [
        'user.json',
        'competition.json',
        'draw_format.json',
        'club.json',
        'person.json',
        'season.json',
        'place.json',
        'division.json',
        'stage.json',
        'team.json',
        'match.json',
    ]

    def setUp(self):
        super(DashboardTests, self).setUp()
        self.url = reverse('admin:index')

    def test_task_0058_most_valuable_widget_no_results(self):
        text = """
        <div class="box half">
            <h1>Awaiting MVP Points</h1>
            <table>
                <thead>
                    <tr>
                        <th>Date/Time</th>
                        <th colspan="2">Match</th>
                    </tr>
                </thead>
                <tbody>
                    <tr class="first odd last">
                        <td colspan="4" class="no_results">No matches awaiting result entry.</td>
                    </tr>
                </tbody>
            </table>
        </div>
        """
        response = self.client.get(self.url)
        self.assertContains(response, text, html=True)

    def test_task_0058_most_valuable_widget_has_results(self):
        # Set a 3-0 scoreline in the match (home team has 4 players)
        m = Match.objects.get(pk=1)
        m.home_team_score = 3
        m.away_team_score = 0
        m.save()

        # Add match statistics for the home team, but no MVP points
        m.statistics.create(mvp=0, number=8, played=1, player_id=1, points=0)
        m.statistics.create(mvp=0, number=3, played=1, player_id=2, points=1)
        m.statistics.create(mvp=0, number=10, played=1, player_id=3, points=1)
        m.statistics.create(mvp=0, number=12, played=1, player_id=4, points=1)

        text = """
        <div class="box half">
            <h1>Awaiting MVP Points</h1>
            <table>
                <thead>
                    <tr>
                        <th>Date/Time</th>
                        <th colspan="2">Match</th>
                    </tr>
                </thead>
                <tbody>
                    <tr class="first odd last multiple-top">
                        <td>01/9/2013</td>
                        <td>Mixed 1</td>
                        <td class="team bare_back_riders">Blue</td>
                        <td><a href="{0}">Edit</a></td>
                    </tr>
                    <tr class="first odd last multiple-bottom">
                        <td>17:45 EST</td>
                        <td><span title="Round Robin">Round 1</span></td>
                        <td class="team ">Green &amp; Gold</td>
                        <td></td>
                    </tr>
                </tbody>
            </table>
        </div>
        """
        response = self.client.get(self.url)
        kwargs = {
            'match_id': m.pk,
            'stage_id': m.stage_id,
            'division_id': m.stage.division_id,
            'season_id': m.stage.division.season_id,
            'competition_id': m.stage.division.season.competition_id,
        }
        link = reverse(
            'admin:competition:competition:season:division:stage:match:detail',
            kwargs=kwargs)

        self.assertContains(response, text.format(link), html=True)
