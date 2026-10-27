from test_plus import TestCase

from tournamentcontrol.competition.models import LadderEntry
from tournamentcontrol.competition.tests.factories import LadderEntryFactory


class LadderEntryFactoryTests(TestCase):
    def test_create(self):
        entry = LadderEntryFactory.create()
        self.assertEqual(LadderEntry.objects.get(), entry)
        self.assertEqual(
            (entry.team, entry.opponent),
            (entry.match.home_team, entry.match.away_team),
        )
