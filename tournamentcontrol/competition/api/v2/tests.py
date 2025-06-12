from test_plus import TestCase
from tournamentcontrol_api import Tournamentcontrol


class StainlessTest(TestCase):
    def test_simple(self):
        client = Tournamentcontrol()
        competitions = client.v2.competition.list()
        self.assertCountEqual(competitions, [])
