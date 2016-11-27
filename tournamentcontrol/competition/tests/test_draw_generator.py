import itertools
import unittest
from datetime import date, datetime

import pytz
from dateutil.rrule import DAILY
from django.test import override_settings
from first import first
from test_plus import TestCase

from tournamentcontrol.competition.draw import (
    DrawGenerator,
    coerce_datetime,
    optimum_tournament_pool_count,
    tournament_date_generator,
    weekly_date_generator,
)
from tournamentcontrol.competition.tests.factories import (
    DivisionFactory,
    StageFactory,
    StageGroupFactory,
    TeamFactory,
)
from tournamentcontrol.competition.utils import single_elimination_final_format

DRAW_FORMAT = """
ROUND
1: 1 vs 2
2: 3 vs 4
ROUND
3: 1 vs 3
4: 4 vs 2
ROUND
5: 1 vs 4
6: 2 vs 3
"""


class DrawGeneratorTest(TestCase):

    def setUp(self):
        DivisionFactory.reset_sequence()
        TeamFactory.reset_sequence()
        StageFactory.reset_sequence()
        StageGroupFactory.reset_sequence()

    def test_bug_0108_stage(self):
        "Ensure DrawGenerator.generate works on Stage objects"
        division = DivisionFactory()
        stages = StageFactory.create_batch(2, division=division)
        teams = TeamFactory.create_batch(4, division=division)

        self.assertEqual(division.stages.count(), 2)
        self.assertEqual(division.teams.count(), 4)
        self.assertEqual(
            list(division.stages.values_list('order', flat=True)), [1, 2])

        generator = DrawGenerator(first(stages), start_date=date(2014, 1, 1))
        generator.parse(DRAW_FORMAT)
        matches = list(generator.generate())
        self.assertEqual(len(matches), 6)

        for m in matches:
            m.save()

        self.assertEqual(
            list(teams[0].matches.values_list('away_team__title', flat=True)),
            ['Team 2', 'Team 3', 'Team 4'])

    def test_bug_0108_stage_group(self):
        "Ensure DrawGenerator.generate works on StageGroup objects"
        division = DivisionFactory(season__mode=DAILY)
        stage = StageFactory(division=division)
        pools = StageGroupFactory.create_batch(2, stage=stage)
        pool = pools[1]
        teams = TeamFactory.create_batch(
            4, division=division, stage_group=pool)

        self.assertTrue(division.stages.filter(order__lt=pool.order))
        self.assertEqual(division.stages.count(), 1)
        self.assertEqual(stage.pools.count(), 2)
        self.assertEqual(division.teams.count(), 4)
        self.assertEqual(pool.teams.count(), 4)

        generator = DrawGenerator(pool, start_date=date(2014, 1, 1))
        generator.parse(DRAW_FORMAT)
        matches = list(generator.generate())
        self.assertEqual(len(matches), 6)

        for m in matches:
            m.save()

        self.assertEqual(
            list(teams[0].matches.values_list('away_team__title', flat=True)),
            ['Team 2', 'Team 3', 'Team 4'])

    def test_bug_0108_division_invalid_mode(self):
        "Ensure DrawGenerator.generate works on Stage object, where Division.mode is not DAILY or WEEKLY"
        division = DivisionFactory(season__mode=0)
        stage = StageFactory(division=division)
        teams = TeamFactory.create_batch(4, division=division)

        generator = DrawGenerator(stage, start_date=date(2014, 1, 1))
        generator.parse(DRAW_FORMAT)
        matches = list(generator.generate(4))
        self.assertEqual(len(matches), 8)

        for m in matches:
            m.save()

        self.assertEqual(
            list(teams[0].matches.values_list('away_team__title', flat=True)),
            [u'Team 2', u'Team 3', u'Team 4', u'Team 2'])


class DrawFunctionTest(TestCase):

    @override_settings(USE_TZ=False)
    def test_coerce_datetime_date_no_tz(self):
        start_date = date(1979, 8, 18)
        self.assertEquals(
            datetime(1979, 8, 18, 0, 0),
            coerce_datetime(start_date))

    @unittest.skip("Validate this test case.")
    @override_settings(USE_TZ=True)
    def test_coerce_datetime_date_tz(self):
        start_date = date(1979, 8, 18)
        self.assertEquals(
            datetime(1979, 8, 18, 0, 0, tzinfo=pytz.UTC),
            coerce_datetime(start_date))

    @override_settings(USE_TZ=False)
    def test_coerce_datetime_datetime_no_tz(self):
        start_date = datetime(1979, 8, 18, 0, 0)
        self.assertEquals(
            datetime(1979, 8, 18, 0, 0),
            coerce_datetime(start_date))

    @unittest.skip("Validate this test case.")
    @override_settings(USE_TZ=True)
    def test_coerce_datetime_datetime_tz(self):
        start_date = datetime(1979, 8, 18, 0, 0)
        self.assertEqual(
            datetime(1979, 8, 18, 0, 0, tzinfo=pytz.UTC),
            coerce_datetime(start_date))

    @override_settings(USE_TZ=False)
    def test_weekly_date_generator(self):
        stage = StageFactory(
            division__season__start_date=date(2015, 3, 30))
        i = itertools.islice(weekly_date_generator(stage), 0, 5)
        self.assertEqual(list(i), [datetime(2015, 3, 30),
                                   datetime(2015, 4, 6),
                                   datetime(2015, 4, 13),
                                   datetime(2015, 4, 20),
                                   datetime(2015, 4, 27)])

    @override_settings(USE_TZ=False)
    def test_weekly_date_generator_season_exclusion(self):
        stage = StageFactory(
            division__season__start_date=date(2015, 3, 30))
        stage.division.season.exclusions.create(date=date(2015, 4, 6))
        i = itertools.islice(weekly_date_generator(stage), 0, 5)
        self.assertEqual(list(i), [datetime(2015, 3, 30),
                                   datetime(2015, 4, 13),
                                   datetime(2015, 4, 20),
                                   datetime(2015, 4, 27),
                                   datetime(2015, 5, 4)])

    @override_settings(USE_TZ=False)
    def test_weekly_date_generator_division_exclusion(self):
        stage = StageFactory(
            division__season__start_date=date(2015, 3, 30))
        stage.division.exclusions.create(date=date(2015, 4, 27))
        i = itertools.islice(weekly_date_generator(stage), 0, 5)
        self.assertEqual(list(i), [datetime(2015, 3, 30),
                                   datetime(2015, 4, 6),
                                   datetime(2015, 4, 13),
                                   datetime(2015, 4, 20),
                                   datetime(2015, 5, 4)])

    @override_settings(USE_TZ=False)
    def test_tournament_date_generator(self):
        stage = StageFactory(
            division__season__mode=DAILY,
            division__season__start_date=date(2015, 3, 30))
        i = itertools.islice(tournament_date_generator(stage), 0, 5)
        self.assertEqual(list(i), [date(2015, 3, 30),
                                   date(2015, 3, 30),
                                   date(2015, 3, 31),
                                   date(2015, 3, 31),
                                   date(2015, 4, 1)])

    @override_settings(USE_TZ=False)
    def test_tournament_date_generator_season_exclusion(self):
        stage = StageFactory(
            division__season__mode=DAILY,
            division__season__start_date=date(2015, 3, 30))
        stage.division.season.exclusions.create(date=date(2015, 3, 31))
        i = itertools.islice(tournament_date_generator(stage), 0, 5)
        self.assertEqual(list(i), [date(2015, 3, 30),
                                   date(2015, 3, 30),
                                   date(2015, 4, 1),
                                   date(2015, 4, 1),
                                   date(2015, 4, 2)])

    @override_settings(USE_TZ=False)
    def test_tournament_date_generator_division_exclusion(self):
        stage = StageFactory(
            division__season__mode=DAILY,
            division__season__start_date=date(2015, 3, 30))
        stage.division.exclusions.create(date=date(2015, 4, 1))
        i = itertools.islice(tournament_date_generator(stage), 0, 5)
        self.assertEqual(list(i), [date(2015, 3, 30),
                                   date(2015, 3, 30),
                                   date(2015, 3, 31),
                                   date(2015, 3, 31),
                                   date(2015, 4, 2)])


class PoolSizeTests(TestCase):

    def test_single_pool(self):
        final_format = (
            'ROUND Semi Final\n'
            '1: P1 vs P4\n'
            '2: P2 vs P3\n'
            'ROUND Final\n'
            '3: W1 vs W2'
        )
        self.assertEqual(1, optimum_tournament_pool_count(5, 2, 4))
        self.assertEqual(
            final_format,
            '\n'.join(map(unicode, single_elimination_final_format(1))),
        )


class TournamentCalculatorTests(TestCase):

    # finishing positions from touch world cup 2015
    world_cup_mixed_teams = '\n'.join([
        "Australia", "New Zealand", "Papua New Guinea", "England", "Samoa",
        "Scotland", "Japan", "France", "Philippines", "Niue", "South Africa",
        "Wales", "Fiji", "Singapore", "United States", "Chile",
        "United Arab Emirates", "Hong Kong", "Italy", "China", "Netherlands",
        "Germany"])

    # finishing positions from european championships 2014
    euros_mixed_teams = '\n'.join([
        "Scotland", "England", "Wales", "Jersey", "France", "Netherlands",
        "Italy", "Guernsey", "Germany", "Switzerland", "Catalonia"])

    # finishing positions from home nations 2013
    home_nations_mixed_teams = '\n'.join([
        "Scotland", "England", "Wales", "Jersey", "Ireland", "Guernsey"])

    def test_large_team_set(self):
        data = {
            'team_hook': self.world_cup_mixed_teams,
            'days_available': 5,
            'max_per_day': 4,
            'min_per_day': 3,
        }
        self.assertGoodView('calculator:index', data=data)

    def test_medium_team_set(self):
        data = {
            'team_hook': self.euros_mixed_teams,
            'days_available': 4,
            'max_per_day': 3,
            'min_per_day': 2,
        }
        self.assertGoodView('calculator:index', data=data)

    def test_small_team_set(self):
        data = {
            'team_hook': self.home_nations_mixed_teams,
            'days_available': 2,
            'max_per_day': 3,
            'min_per_day': 2,
        }
        self.assertGoodView('calculator:index', data=data)
