import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone
from test_plus import TestCase

from tournamentcontrol.competition.compops import queries
from tournamentcontrol.competition.tests import factories

TZ = ZoneInfo("Australia/Brisbane")
DAY = datetime.date(2026, 10, 8)


def at(hour, minute=0):
    return timezone.make_aware(datetime.datetime(2026, 10, 8, hour, minute), TZ)


class DayFixture(TestCase):
    def setUp(self):
        super().setUp()
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
        self.assertIs(slot.open, False)

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
        self.assertIs(slots[1].is_byes, True)
        self.assertIs(slots[1].open, False)

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
        (match,) = queries.day_scorers(self.season, DAY)
        self.assertEqual((match, match.out_of_balance), (scored, False))

    def test_balanced_match_is_not_listed(self):
        scored = self.match(8, home_team_score=1, away_team_score=0)
        self._stat(scored, scored.home_team, 1)
        self.assertEqual(list(queries.day_scorers(self.season, DAY)), [])

    def test_out_of_balance_match_is_listed(self):
        scored = self.match(8, home_team_score=2, away_team_score=0)
        self._stat(scored, scored.home_team, 1)
        (match,) = queries.day_scorers(self.season, DAY)
        self.assertEqual((match, match.out_of_balance), (scored, True))

    def test_statistics_without_points_are_out_of_balance(self):
        scored = self.match(8, home_team_score=1, away_team_score=0)
        self._stat(scored, scored.home_team, None)
        (match,) = queries.day_scorers(self.season, DAY)
        self.assertEqual((match, match.out_of_balance), (scored, True))

    def test_match_with_many_statistics_is_listed_once(self):
        scored = self.match(8, home_team_score=3, away_team_score=0)
        self._stat(scored, scored.home_team, 1)
        self._stat(scored, scored.home_team, 1)
        self.assertEqual(list(queries.day_scorers(self.season, DAY)), [scored])

    def test_season_without_statistics_lists_nothing(self):
        self.season.statistics = False
        self.season.save()
        self.match(8, home_team_score=3, away_team_score=1)
        self.assertEqual(list(queries.day_scorers(self.season, DAY)), [])


class DayStreamsTests(DayFixture):
    def test_current_and_next_per_streamed_ground(self):
        # An earlier streamed match that must not be current.
        self.match(8, ground=self.field1, live_stream=True, external_identifier="a")
        current = self.match(
            9, ground=self.field1, live_stream=True, external_identifier="b"
        )
        following = self.match(10, ground=self.field1, live_stream=True)
        self.match(9, ground=self.field2)
        grounds, _ = queries.day_streams(self.season, DAY, at(9, 30))
        (gs,) = grounds
        self.assertEqual(gs.ground, self.field1)
        self.assertEqual(gs.current, current)
        self.assertEqual(gs.next, following)

    def test_before_first_match_there_is_no_current(self):
        first = self.match(9, ground=self.field1, live_stream=True)
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

    def test_streamed_grounds_cost_one_query_for_their_matches(self):
        field3 = factories.GroundFactory.create(
            venue=self.venue, title="Field 3", live_stream=True
        )
        field4 = factories.GroundFactory.create(
            venue=self.venue, title="Field 4", live_stream=True
        )
        for ground in (self.field1, field3, field4):
            self.match(8, ground=ground, live_stream=True)
            self.match(9, ground=ground, live_stream=True)
        factories.LiveStreamEventFactory.create(season=self.season, start=at(17))
        # The grounds, their matches, and the day's events.
        with self.assertNumQueries(3):
            grounds, events = queries.day_streams(self.season, DAY, at(8, 30))
            list(events)
        self.assertEqual(
            [(gs.ground, gs.current.time, gs.next.time) for gs in grounds],
            [
                (self.field1, datetime.time(8), datetime.time(9)),
                (field3, datetime.time(8), datetime.time(9)),
                (field4, datetime.time(8), datetime.time(9)),
            ],
        )


class GroundDayTests(DayFixture):
    def _on(self, day, hour):
        when = at(hour) + (day - DAY)
        return factories.MatchFactory.create(
            stage=self.stage,
            play_at=self.field1,
            live_stream=True,
            date=day,
            time=datetime.time(hour),
            datetime=when,
        )

    def test_previous_current_next(self):
        a = self.match(8, ground=self.field1, live_stream=True)
        b = self.match(9, ground=self.field1, live_stream=True)
        c = self.match(10, ground=self.field1, live_stream=True)
        self.assertEqual(queries.ground_day(self.field1, DAY, at(9, 15)), (a, b, c))

    def test_match_not_streamed_is_skipped_but_stays_on_the_runsheet(self):
        # A stale identifier outlives the opt-in until the broadcast is gone.
        a = self.match(8, ground=self.field1, live_stream=True)
        unstreamed = self.match(9, ground=self.field1, external_identifier="old")
        c = self.match(10, ground=self.field1, live_stream=True)
        self.assertEqual(queries.ground_day(self.field1, DAY, at(9, 15)), (None, a, c))
        (gs,), _ = queries.day_streams(self.season, DAY, at(9, 15))
        self.assertEqual((gs.current, gs.next), (a, c))
        self.assertEqual(
            list(queries.ground_runsheet(self.field1, DAY)), [a, unstreamed, c]
        )

    def test_next_never_crosses_the_day(self):
        b = self.match(9, ground=self.field1, live_stream=True)
        factories.MatchFactory.create(
            stage=self.stage,
            play_at=self.field1,
            live_stream=True,
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


class ThumbnailDeferredTests(DayFixture):
    """
    The stream thumbnails are blobs CompOps never shows. A large season
    thumbnail fetched once per match row exhausted a worker's memory (#654).
    """

    def setUp(self):
        super().setUp()
        self.streamed = self.match(8, ground=self.field1, live_stream=True)

    def assertThumbnailsDeferred(self, match):
        deferred = {"live_stream_thumbnail_image"}
        self.assertEqual(
            (
                match.get_deferred_fields(),
                match.stage.division.season.get_deferred_fields(),
            ),
            (deferred, deferred),
        )

    def test_every_match_read_leaves_the_thumbnails_behind(self):
        (gs,), _ = queries.day_streams(self.season, DAY, at(8, 30))
        reads = {
            "day_matches": queries.day_matches(self.season, DAY).get(),
            "day_streams": gs.current,
            "ground_day": queries.ground_day(self.field1, DAY, at(8, 30))[1],
            "ground_runsheet": queries.ground_runsheet(self.field1, DAY).get(),
            "team_results": queries.team_results(self.streamed.home_team).get(),
        }
        for name, match in reads.items():
            with self.subTest(name):
                self.assertThumbnailsDeferred(match)


class EventsTests(TestCase):
    """The home page's seasons: playing now, coming up, recently finished."""

    NOW = at(9)

    def season(self, *days, **kwargs):
        kwargs.setdefault("timezone", "Australia/Brisbane")
        season = factories.SeasonFactory.create(**kwargs)
        stage = factories.StageFactory.create(division__season=season)
        for day in days:
            factories.MatchFactory.create(stage=stage, date=day)
        return season

    def test_seasons_are_grouped_by_when_they_are_played(self):
        # Today, 8 October, is a rest day of the season being played.
        current = self.season(datetime.date(2026, 10, 7), datetime.date(2026, 10, 10))
        later = self.season(datetime.date(2026, 12, 1))
        soon = self.season(datetime.date(2026, 10, 20))
        older = self.season(datetime.date(2026, 9, 1))
        recent = self.season(datetime.date(2026, 9, 30), datetime.date(2026, 10, 1))
        self.season()
        events = queries.events(self.NOW)
        self.assertEqual(
            (events.current, events.upcoming, events.recent),
            ([current], [soon, later], [recent, older]),
        )
        self.assertEqual(
            (
                events.current[0].compops_next_day,
                [s.compops_days for s in events.upcoming],
                [s.compops_days for s in events.recent],
            ),
            (datetime.date(2026, 10, 10), [12, 54], [7, 37]),
        )

    def test_a_match_today_is_the_next_day(self):
        self.season(DAY)
        (season,) = queries.events(self.NOW).current
        self.assertEqual(season.compops_next_day, DAY)

    def test_today_is_the_date_where_the_season_is_played(self):
        # 22:00 on the 8th in Brisbane is already the 9th in Auckland.
        tomorrow = datetime.date(2026, 10, 9)
        brisbane = self.season(tomorrow)
        auckland = self.season(tomorrow, timezone="Pacific/Auckland")
        events = queries.events(at(22))
        self.assertEqual((events.current, events.upcoming), ([auckland], [brisbane]))

    def test_every_season_is_listed_under_its_competition(self):
        empty = self.season(competition__title="Atlantic Cup")
        old = self.season(datetime.date(2024, 5, 1), competition__title="Pacific Cup")
        new = self.season(
            datetime.date(2026, 10, 7),
            competition=old.competition,
            enabled=False,
        )
        events = queries.events(self.NOW)
        self.assertEqual(
            events.competitions,
            [(empty.competition, [empty]), (old.competition, [new, old])],
        )

    def test_recent_and_upcoming_are_limited(self):
        upcoming = [self.season(datetime.date(2026, 11, n)) for n in (1, 2, 3)]
        recent = [self.season(datetime.date(2026, 9, n)) for n in (3, 2, 1)]
        events = queries.events(self.NOW, limit=2)
        self.assertEqual((events.upcoming, events.recent), (upcoming[:2], recent[:2]))

    def test_two_queries_however_many_seasons(self):
        for n in (6, 7, 8):
            self.season(datetime.date(2026, 10, n), datetime.date(2026, 10, 9))
        with self.assertNumQueries(2):
            events = queries.events(self.NOW)
        self.assertEqual(
            [s.get_deferred_fields() for s in events.current],
            [{"live_stream_thumbnail_image"}] * 3,
        )


class SeasonDaysTests(DayFixture):
    def test_days_carry_their_matches_and_results(self):
        yesterday = DAY - datetime.timedelta(days=1)
        tomorrow = DAY + datetime.timedelta(days=1)
        last_week = DAY - datetime.timedelta(days=7)
        for score in (1, None):
            factories.MatchFactory.create(
                stage=self.stage,
                date=last_week,
                home_team_score=score,
                away_team_score=score,
            )
        factories.MatchFactory.create(
            stage=self.stage, date=yesterday, home_team_score=1, away_team_score=0
        )
        self.match(8)
        factories.MatchFactory.create(stage=self.stage, date=tomorrow)
        factories.MatchFactory.create(stage=self.stage, date=None)
        with self.assertNumQueries(1):
            days, undated = queries.season_days(self.season, at(9))
        self.assertEqual(
            [(d.date, d.matches, d.entered, d.status) for d in days],
            [
                (last_week, 2, 1, "overdue"),
                (yesterday, 1, 1, "complete"),
                (DAY, 1, 0, "today"),
                (tomorrow, 1, 0, "upcoming"),
            ],
        )
        self.assertEqual(undated, 1)

    def test_adjacent_days_are_the_nearest_with_matches(self):
        before = DAY - datetime.timedelta(days=3)
        after = DAY + datetime.timedelta(days=2)
        for day in (before, DAY, after, after + datetime.timedelta(days=1)):
            factories.MatchFactory.create(stage=self.stage, date=day)
        # Another season's match, nearer than either.
        factories.MatchFactory.create(date=DAY + datetime.timedelta(days=1))
        self.assertEqual(
            (
                queries.adjacent_days(self.season, DAY),
                queries.adjacent_days(self.season, before),
            ),
            ((before, after), (None, DAY)),
        )
