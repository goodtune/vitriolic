import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone
from freezegun import freeze_time
from test_plus import TestCase

from tournamentcontrol.competition.dashboard import (
    matches_require_basic_results,
    matches_require_progression,
)
from tournamentcontrol.competition.tests.factories import (
    MatchFactory,
    StageFactory,
    TeamFactory,
)


class BasicResultTests(TestCase):
    @freeze_time("2019-07-15 09:00 UTC")
    def test_bare_all_in_utc(self):
        match = MatchFactory.create(
            datetime=datetime.datetime(
                2019, 7, 15, 8, 30, tzinfo=datetime.timezone.utc
            ),
            stage__division__season__timezone="UTC",
        )
        self.assertCountEqual(matches_require_basic_results(), [match])

    @freeze_time("2019-07-15 09:00 +13")
    def test_bare_match_in_samoa(self):
        tzname = "Pacific/Apia"
        tzinfo = ZoneInfo(tzname)
        match = MatchFactory.create(
            datetime=timezone.make_aware(datetime.datetime(2019, 7, 15, 8, 30), tzinfo),
            stage__division__season__timezone=tzname,
        )
        self.assertCountEqual(matches_require_basic_results(), [match])

    @freeze_time("2019-07-15 09:00 +13")
    def test_bare_match_in_samoa_bye(self):
        tzname = "Pacific/Apia"
        tzinfo = ZoneInfo(tzname)
        match = MatchFactory.create(
            round=1,
            is_bye=True,
            away_team=None,
            datetime=None,
            date=datetime.date(2019, 7, 15),
            time=None,
            stage__division__season__timezone=tzname,
        )
        # A bye's would never exist in isolation.
        MatchFactory.create(
            round=1,
            datetime=timezone.make_aware(datetime.datetime(2019, 7, 15, 8, 30), tzinfo),
            stage=match.stage,
            home_team_score=5,
            away_team_score=4,
        )
        self.assertCountEqual(matches_require_basic_results(), [match])


@freeze_time("2019-07-15 09:30 UTC")
class RequireProgression(TestCase):
    def test_trivial(self):
        # Need two match times, one in the past and one in the future.
        dt1 = datetime(2019, 7, 15, 8, 30, tzinfo=timezone.utc)
        dt2 = datetime(2019, 7, 15, 10, 30, tzinfo=timezone.utc)

        # Create a stage with four teams to play each other and then progress
        # the winners to a final.
        stage = StageFactory.create(division__season__timezone="UTC")
        t1, t2, t3, t4 = TeamFactory.create_batch(4, division=stage.division)

        # Semi Final
        m1 = MatchFactory.create(
            home_team=t1, away_team=t4, datetime=dt1, label="Semi 1"
        )
        m2 = MatchFactory.create(
            home_team=t2, away_team=t3, datetime=dt1, label="Semi 2"
        )
        # Final
        m3 = MatchFactory.create(
            home_team=None,
            away_team=None,
            home_team_eval="W",
            home_team_eval_related=m1,
            away_team_eval="W",
            away_team_eval_related=m2,
            datetime=dt2,
            label="Final",
        )

        result_required = matches_require_basic_results()
        require_progression = matches_require_progression()
        self.assertCountEqual(result_required, [m1, m2])
        self.assertCountEqual(require_progression, [m3])

        # Home teams win both matches 4-3
        for match in [m1, m2]:
            match.home_team_score = 4
            match.away_team_score = 3
            match.save()

        result_required = matches_require_basic_results()
        require_progression = matches_require_progression()
        self.assertCountEqual(result_required, [])
        self.assertCountEqual(require_progression, [m3])

        m3.home_team, m3.away_team = m1.home_team, m2.home_team
        m3.save()

        result_required = matches_require_basic_results()
        require_progression = matches_require_progression()
        self.assertCountEqual(result_required, [])
        self.assertCountEqual(require_progression, [])
