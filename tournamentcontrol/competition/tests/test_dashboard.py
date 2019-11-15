from datetime import date, datetime

import pytz
from django.utils import timezone
from freezegun import freeze_time
from test_plus import TestCase
from tournamentcontrol.competition.dashboard import matches_require_basic_results
from tournamentcontrol.competition.tests.factories import MatchFactory


class BasicResultTests(TestCase):
    @freeze_time("2019-07-15 09:00 UTC")
    def test_bare_all_in_utc(self):
        match = MatchFactory.create(
            datetime=datetime(2019, 7, 15, 8, 30, tzinfo=timezone.utc),
            stage__division__season__timezone="UTC",
        )
        self.assertCountEqual(matches_require_basic_results(), [match])

    @freeze_time("2019-07-15 09:00 +13")
    def test_bare_match_in_samoa(self):
        tzname = "Pacific/Apia"
        tzinfo = pytz.timezone(tzname)
        match = MatchFactory.create(
            datetime=timezone.make_aware(datetime(2019, 7, 15, 8, 30), tzinfo),
            stage__division__season__timezone=tzname,
        )
        self.assertCountEqual(matches_require_basic_results(), [match])

    @freeze_time("2019-07-15 09:00 +13")
    def test_bare_match_in_samoa_bye(self):
        tzname = "Pacific/Apia"
        tzinfo = pytz.timezone(tzname)
        match = MatchFactory.create(
            round=1,
            is_bye=True,
            away_team=None,
            datetime=None,
            date=date(2019, 7, 15),
            time=None,
            stage__division__season__timezone=tzname,
        )
        # A bye's would never exist in isolation.
        MatchFactory.create(
            round=1,
            datetime=timezone.make_aware(datetime(2019, 7, 15, 8, 30), tzinfo),
            stage=match.stage,
            home_team_score=5,
            away_team_score=4,
        )
        self.assertCountEqual(matches_require_basic_results(), [match])
