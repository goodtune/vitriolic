from datetime import time

from django.test.testcases import TestCase

from tournamentcontrol.competition.models import Stage
from tournamentcontrol.competition.utils import (
    round_robin_format,
    stage_group_position as sgp,
    time_choice,
)


class DrawFormatTests(TestCase):

    def test_round_robin_format_even(self):
        text = """ROUND
1: White vs Beige
2: Off White vs Bone
3: Cream vs Ivory
ROUND
4: White vs Bone
5: Beige vs Ivory
6: Off White vs Cream
ROUND
7: White vs Ivory
8: Bone vs Cream
9: Beige vs Off White
ROUND
10: White vs Cream
11: Ivory vs Off White
12: Bone vs Beige
ROUND
13: White vs Off White
14: Cream vs Beige
15: Ivory vs Bone"""
        fmt = round_robin_format(
            ["White", "Off White", "Cream", "Ivory", "Bone", "Beige"])
        self.assertEqual(fmt, text)

    def test_round_robin_format_uneven(self):
        text = """ROUND
1: 1 vs 0
2: 2 vs 3
ROUND
3: 1 vs 3
4: 0 vs 2
ROUND
5: 1 vs 2
6: 3 vs 0"""
        fmt = round_robin_format([1, 2, 3])
        self.assertEqual(fmt, text)


class OpponentTests(TestCase):

    fixtures = [
        'competition.json',
        'club.json',
        'person.json',
        'season.json',
        'place.json',
        'division.json',
        'stage.json',
        'team.json',
        'match.json',
    ]


class StageGroupPositionTests(TestCase):

    fixtures = [
        'competition.json',
        'club.json',
        'person.json',
        'season.json',
        'place.json',
        'division.json',
        'stage.json',
        'team.json',
        'match.json',
    ]

    def setUp(self):
        super(StageGroupPositionTests, self).setUp()
        self.s1 = Stage.objects.get(pk=1)
        self.s2 = Stage.objects.get(pk=2)
        self.s3 = Stage.objects.get(pk=3)

    def test_invalid(self):
        "Invalid StageGroupPosition formula must throw ValueError"
        with self.assertRaises(ValueError):
            sgp(self.s1, '1')

    def test_position(self):
        "Pn formula must return from predecessor stage"
        with self.assertRaises(Stage.DoesNotExist):
            res = sgp(self.s1, 'P1')

        res = sgp(self.s2, 'P2')
        self.assertEqual(res, (self.s1, None, 2))

        res = sgp(self.s3, 'P3')
        self.assertEqual(res, (self.s2, None, 3))

    def test_stage_position(self):
        "SnPn formula must return from specified stage"
        with self.assertRaises(AssertionError):
            # Negative indexing is not supported.
            res = sgp(self.s1, 'S0P1')

        res = sgp(self.s2, 'S1P2')
        self.assertEqual(res, (self.s1, None, 2))

        res = sgp(self.s3, 'S1P3')
        self.assertEquals(res, (self.s1, None, 3))

        with self.assertRaises(IndexError):
            res = sgp(self.s2, 'S4P4')

    def test_group_position(self):
        "GnPn formula must return from specified group in predecessor stage"
        # TODO add StageGroup fixtures and test case

    def test_stage_group_position(self):
        "SnGnPn formula must return from specified stage & group"
        # TODO add StageGroup fixtures and test case


class UtilityTests(TestCase):

    def test_time_choice_8am(self):
        t = time_choice(time(8, 0))
        self.assertEqual(t, (("08:00:00", "08:00")))

    def test_time_choice_8pm(self):
        t = time_choice(time(20, 0))
        self.assertEqual(t, (("20:00:00", "20:00")))
