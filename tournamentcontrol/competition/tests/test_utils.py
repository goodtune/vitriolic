import textwrap

from django.test import TestCase

from tournamentcontrol.competition import utils


class MessagesTestMixin:
    """
    Mixin stub for testing Django messages.

    Drop once we no longer support Django < 5.0.
    """

    def assertMessages(self, *args, **kwargs): ...


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

    def test_round_robin_format_integer_input(self):
        """Test that integer input works correctly."""
        result = utils.round_robin_format(4)
        expected = textwrap.dedent(
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
        ).strip()
        self.assertEqual(expected, result)

    def test_round_robin_format_integer_equals_range(self):
        """Test that round_robin_format(4) equals round_robin_format(range(1, 5))."""
        self.assertEqual(
            utils.round_robin_format(4), utils.round_robin_format(range(1, 5))
        )

    def test_round_robin_format_integer_equals_list(self):
        """Test that round_robin_format(4) equals round_robin_format([1, 2, 3, 4])."""
        self.assertEqual(
            utils.round_robin_format(4), utils.round_robin_format([1, 2, 3, 4])
        )

    def test_round_robin_format_different_sizes(self):
        """Test various team counts to ensure flexibility."""
        # Test with 3 teams (odd number)
        result_3_int = utils.round_robin_format(3)
        result_3_list = utils.round_robin_format([1, 2, 3])
        self.assertEqual(result_3_int, result_3_list)

        # Test with 6 teams
        result_6_int = utils.round_robin_format(6)
        result_6_range = utils.round_robin_format(range(1, 7))
        self.assertEqual(result_6_int, result_6_range)

    def test_round_robin_format_custom_teams(self):
        """Test with custom team identifiers."""
        teams = ["Team A", "Team B", "Team C", "Team D"]
        result = utils.round_robin_format(teams)
        self.assertIn("Team A vs Team D", result)
        self.assertIn("Team B vs Team C", result)

    def test_round_robin_format_with_rounds_parameter(self):
        """Test that the rounds parameter works with both integer and iterable inputs."""
        # Test with integer input and rounds parameter
        result_int = utils.round_robin_format(4, rounds=1)
        result_list = utils.round_robin_format([1, 2, 3, 4], rounds=1)
        self.assertEqual(result_int, result_list)

        # Should only contain the first round
        self.assertEqual(result_int.count("ROUND"), 1)

    def test_round_robin_format_edge_cases(self):
        """Test edge cases."""
        # Single team (though this might not be practical)
        result_1 = utils.round_robin_format(1)
        # Should handle gracefully (will have a bye with 0)
        self.assertIsInstance(result_1, str)

        # Two teams
        result_2_int = utils.round_robin_format(2)
        result_2_list = utils.round_robin_format([1, 2])
        self.assertEqual(result_2_int, result_2_list)

    def test_sum_dict_integer(self):
        d1 = utils.SumDict({"a": 1, "b": 2})
        d2 = utils.SumDict({"b": 1, "c": 2})
        self.assertEqual(d1 + d2, utils.SumDict({"a": 1, "b": 3, "c": 2}))

    def test_revpow(self):
        self.assertEqual(utils.revpow(2**4, 2), 4)
