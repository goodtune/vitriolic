from django.test.utils import override_settings
from django.test import TestCase
from tournamentcontrol.competition.tests import factories

@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class DivisionAPITests(TestCase):
    def test_division_timezone_serialization(self):
        match = factories.MatchFactory.create()
        division = match.stage.division
        url = (
            f"/api/v1/competitions/{division.season.competition.slug}/"
            f"seasons/{division.season.slug}/divisions/{division.slug}/"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        timezone_str = getattr(division.season.timezone, "key", str(division.season.timezone))
        self.assertEqual(
            data["stages"][0]["matches"][0]["play_at"]["timezone"],
            timezone_str,
        )
