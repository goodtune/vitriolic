import pickle

from test_plus import TestCase

from tournamentcontrol.competition import sites


class ApplicationPickleTest(TestCase):

    def test_competition_site(self):
        p = pickle.dumps(sites.competition)
        self.assertTrue(p)

    def test_registration_site(self):
        p = pickle.dumps(sites.registration)
        self.assertTrue(p)

    def test_calculator_site(self):
        p = pickle.dumps(sites.calculator)
        self.assertTrue(p)
