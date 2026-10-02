import decimal

from django.test import SimpleTestCase

from tournamentcontrol.competition.calc import BonusPointCalculator, Calculator


class Entry:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class CalculatorTests(SimpleTestCase):
    def test_points_formula(self):
        calculator = Calculator(Entry(win=1, draw=0, loss=0))
        calculator.parse("3*win + 2*draw + 1*loss")
        self.assertEqual(decimal.Decimal(3), calculator.evaluate())

    def test_identifiers(self):
        calculator = Calculator(Entry())
        calculator.parse("3*win + 2*draw + 1*loss")
        self.assertEqual({"win", "draw", "loss"}, calculator.identifiers())


class BonusPointCalculatorTests(SimpleTestCase):
    formula = "[win=1, score_against=0, forfeit_for=0: 1] + [loss=1, margin<=2: 1]"

    def _bonus(self, **kwargs):
        calculator = BonusPointCalculator(Entry(**kwargs))
        calculator.parse(self.formula)
        return calculator.evaluate()

    def test_narrow_loss(self):
        self.assertEqual(
            1, self._bonus(win=0, loss=1, score_for=4, score_against=5, margin=1)
        )

    def test_two_point_loss(self):
        self.assertEqual(
            1, self._bonus(win=0, loss=1, score_for=5, score_against=7, margin=2)
        )

    def test_wide_loss(self):
        self.assertEqual(
            0, self._bonus(win=0, loss=1, score_for=3, score_against=7, margin=4)
        )

    def test_shutout_loss(self):
        self.assertEqual(
            0, self._bonus(win=0, loss=1, score_for=0, score_against=6, margin=6)
        )

    def test_shutout_win(self):
        self.assertEqual(
            1,
            self._bonus(
                win=1, loss=0, forfeit_for=0, score_for=6, score_against=0, margin=6
            ),
        )

    def test_identifiers(self):
        calculator = BonusPointCalculator(Entry())
        calculator.parse(self.formula)
        self.assertEqual(
            {"win", "score_against", "forfeit_for", "loss", "margin"},
            calculator.identifiers(),
        )
