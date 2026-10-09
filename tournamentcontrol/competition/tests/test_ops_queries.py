import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone
from test_plus import TestCase

from tournamentcontrol.competition.ops import queries
from tournamentcontrol.competition.tests import factories

TZ = ZoneInfo("Australia/Brisbane")
DAY = datetime.date(2026, 10, 8)


def at(hour, minute=0):
    return timezone.make_aware(datetime.datetime(2026, 10, 8, hour, minute), TZ)


class DayFixture(TestCase):
    def setUp(self):
        self.season = factories.SeasonFactory.create(timezone="Australia/Brisbane")
        self.venue = factories.VenueFactory.create(season=self.season)
        self.field1 = factories.GroundFactory.create(
            venue=self.venue, title="Field 1", live_stream=True
        )
        self.field2 = factories.GroundFactory.create(venue=self.venue, title="Field 2")
        self.stage = factories.StageFactory.create(division__season=self.season)

    def match(self, hour, minute=0, ground=None, **kwargs):
        when = at(hour, minute)
        return factories.MatchFactory.create(
            stage=self.stage,
            datetime=when,
            date=DAY,
            time=when.time(),
            play_at=ground or self.field2,
            **kwargs,
        )


class DayResultsTests(DayFixture):
    def test_slots_group_by_time_and_the_earliest_incomplete_opens(self):
        self.match(8, home_team_score=1, away_team_score=0)
        self.match(8, 40, home_team_score=2, away_team_score=2)
        self.match(8, 40)
        self.match(9, 20)
        slots = queries.day_results(self.season, DAY)
        self.assertEqual([s.key for s in slots], ["0800", "0840", "0920"])
        self.assertEqual(
            [s.state for s in slots], ["complete", "in_progress", "pending"]
        )
        self.assertEqual([s.open for s in slots], [False, True, False])
        self.assertEqual((slots[1].entered, slots[1].total), (1, 2))

    def test_all_complete_opens_nothing(self):
        self.match(8, home_team_score=1, away_team_score=0)
        (slot,) = queries.day_results(self.season, DAY)
        self.assertFalse(slot.open)

    def test_unscheduled_matches_land_in_a_trailing_slot(self):
        self.match(8)
        factories.MatchFactory.create(
            stage=self.stage, date=DAY, time=None, datetime=None
        )
        slots = queries.day_results(self.season, DAY)
        self.assertEqual([s.key for s in slots], ["0800", "unscheduled"])
        self.assertEqual(slots[1].label, "Unscheduled")

    def test_byes_are_a_trailing_slot_and_never_open(self):
        self.match(8)
        factories.MatchFactory.create(
            stage=self.stage,
            date=DAY,
            is_bye=True,
            away_team=None,
            time=None,
            datetime=None,
        )
        slots = queries.day_results(self.season, DAY)
        self.assertEqual([s.key for s in slots], ["0800", "byes"])
        self.assertTrue(slots[1].is_byes)
        self.assertFalse(slots[1].open)

    def test_other_days_and_seasons_excluded(self):
        self.match(8)
        factories.MatchFactory.create(
            stage=self.stage, date=DAY + datetime.timedelta(days=1)
        )
        factories.MatchFactory.create(date=DAY)
        (slot,) = queries.day_results(self.season, DAY)
        self.assertEqual(slot.total, 1)

    def test_slot_for(self):
        self.match(8)
        self.assertEqual(queries.slot_for(self.season, DAY, "0800").key, "0800")
        self.assertIsNone(queries.slot_for(self.season, DAY, "0900"))


class DayScorersTests(DayFixture):
    def setUp(self):
        super().setUp()
        self.season.statistics = True
        self.season.save()

    def _stat(self, match, team, points):
        person = factories.PersonFactory.create()
        factories.TeamAssociationFactory.create(team=team, person=person, number=1)
        factories.SimpleScoreMatchStatisticFactory.create(
            match=match, player=person, number=1, played=1, points=points
        )

    def test_scored_match_without_statistics_is_listed(self):
        scored = self.match(8, home_team_score=3, away_team_score=1)
        self.match(8)
        self.assertEqual(list(queries.day_scorers(self.season, DAY)), [scored])

    def test_balanced_match_is_not_listed(self):
        scored = self.match(8, home_team_score=1, away_team_score=0)
        self._stat(scored, scored.home_team, 1)
        self.assertEqual(list(queries.day_scorers(self.season, DAY)), [])

    def test_out_of_balance_match_is_listed(self):
        scored = self.match(8, home_team_score=2, away_team_score=0)
        self._stat(scored, scored.home_team, 1)
        (match,) = queries.day_scorers(self.season, DAY)
        self.assertEqual(match, scored)
        self.assertTrue(queries.out_of_balance(match))

    def test_season_without_statistics_lists_nothing(self):
        self.season.statistics = False
        self.season.save()
        self.match(8, home_team_score=3, away_team_score=1)
        self.assertEqual(list(queries.day_scorers(self.season, DAY)), [])


class DayStreamsTests(DayFixture):
    def test_current_and_next_per_streamed_ground(self):
        early = self.match(8, ground=self.field1, external_identifier="a")
        current = self.match(9, ground=self.field1, external_identifier="b")
        following = self.match(10, ground=self.field1)
        self.match(9, ground=self.field2)
        grounds, _ = queries.day_streams(self.season, DAY, at(9, 30))
        (gs,) = grounds
        self.assertEqual(gs.ground, self.field1)
        self.assertEqual(gs.current, current)
        self.assertEqual(gs.next, following)
        self.assertNotEqual(gs.current, early)

    def test_before_first_match_there_is_no_current(self):
        first = self.match(9, ground=self.field1)
        (gs,), _ = queries.day_streams(self.season, DAY, at(7))
        self.assertIsNone(gs.current)
        self.assertEqual(gs.next, first)

    def test_season_events_for_the_day(self):
        today = factories.LiveStreamEventFactory.create(
            season=self.season, start=at(17)
        )
        factories.LiveStreamEventFactory.create(
            season=self.season, start=at(17) + datetime.timedelta(days=1)
        )
        _, events = queries.day_streams(self.season, DAY, at(9))
        self.assertEqual(list(events), [today])


class GroundDayTests(DayFixture):
    def _on(self, day, hour):
        when = at(hour) + (day - DAY)
        return factories.MatchFactory.create(
            stage=self.stage,
            play_at=self.field1,
            date=day,
            time=datetime.time(hour),
            datetime=when,
        )

    def test_previous_current_next(self):
        a = self.match(8, ground=self.field1)
        b = self.match(9, ground=self.field1)
        c = self.match(10, ground=self.field1)
        self.assertEqual(queries.ground_day(self.field1, DAY, at(9, 15)), (a, b, c))

    def test_next_never_crosses_the_day(self):
        b = self.match(9, ground=self.field1)
        factories.MatchFactory.create(
            stage=self.stage,
            play_at=self.field1,
            date=DAY + datetime.timedelta(days=1),
            time=datetime.time(8),
            datetime=at(8) + datetime.timedelta(days=1),
        )
        self.assertEqual(
            queries.ground_day(self.field1, DAY, at(9, 15)), (None, b, None)
        )

    def test_future_day_has_no_current_match(self):
        tomorrow = DAY + datetime.timedelta(days=1)
        first = self._on(tomorrow, 8)
        self._on(tomorrow, 10)
        self.assertEqual(
            queries.ground_day(self.field1, tomorrow, at(9, 30)), (None, None, first)
        )

    def test_past_day_current_is_the_last_match(self):
        yesterday = DAY - datetime.timedelta(days=1)
        first = self._on(yesterday, 8)
        last = self._on(yesterday, 10)
        self.assertEqual(
            queries.ground_day(self.field1, yesterday, at(9, 30)), (first, last, None)
        )
