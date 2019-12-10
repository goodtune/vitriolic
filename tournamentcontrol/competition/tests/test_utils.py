import textwrap

from django.test import TestCase
from tournamentcontrol.competition import utils


class UtilTests(TestCase):
    def test_round_robin_even(self):
        self.assertEqual(
            [[(1, 4), (2, 3)], [(1, 3), (4, 2)], [(1, 2), (3, 4)]],
            utils.round_robin(range(1, 5)),
        )

    def test_round_robin_odd(self):
        self.assertEqual(
            [[(1, 0), (2, 3)], [(1, 3), (0, 2)], [(1, 2), (3, 0)]],
            
            utils.round_robin(range(1, 4)),
        )

    def test_round_robin_format_even(self):
        self.assertEqual(
            textwrap.dedent(
                """
                ROUND
                1: 1 vs 4
                2: 2 vs 3
                ROUND
                3: 1 vs 3
                4: 4 vs 2
                ROUND
                5: 1 vs 2
                6: 3 vs 4
                """
            ).strip(),
            utils.round_robin_format(range(1, 5)),
        )

    def test_sum_dict_integer(self):
        d1 = utils.SumDict({"a": 1, "b": 2})
        d2 = utils.SumDict({"b": 1, "c": 2})
        self.assertEqual(d1 + d2, utils.SumDict({"a": 1, "b": 3, "c": 2}))

    def test_revpow(self):
        self.assertEqual(utils.revpow(2 ** 4, 2), 4)
