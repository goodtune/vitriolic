from test_plus import TestCase
from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.models import Season, Division


class CloneTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create(is_staff=True, is_superuser=True)
        cls.season = factories.SeasonFactory.create()
        cls.divisions = factories.DivisionFactory.create_batch(2, season=cls.season)

    def test_season(self):
        "1 season with 2 divisions, clone results in 2 seasons 4 divisions"
        self.assertEqual(Season.objects.count(), 1)
        self.assertEqual(Division.objects.count(), 2)

        print Season.objects.values_list('pk', 'title')
        print Division.objects.values_list('pk', 'title', 'season_id')

        self.season.clone(attrs={'title': 'My New Season'})

        print Season.objects.values_list('pk', 'title')
        print Division.objects.values_list('pk', 'title', 'season_id')

        self.assertEqual(Season.objects.count(), 2)
        self.assertEqual(Division.objects.count(), 4)
