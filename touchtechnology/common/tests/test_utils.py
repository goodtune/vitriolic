from decimal import Decimal
from unittest import skipIf

import six
from test_plus import TestCase
from touchtechnology.common.forms import boolean_choice_field_coerce
from touchtechnology.common.utils import average, get_mod_func, timezone_choice


class Average(TestCase):

    def test_integers(self):
        series = (1, 2, 3, 4)
        res = average(series)
        self.assertEqual(res, 2.5)

    def test_floats(self):
        series = (1.25, 1.5, 1.75)
        res = average(series)
        self.assertEqual(res, 1.5)

    @skipIf(six.PY3, "Floating point's seem to have changed?")
    def test_complex_floats(self):
        series = (5.0 / 3, 35.0 / 6, 22.0 / 7)
        res = average(series)
        self.assertEqual(res, Decimal('3.54761904762'))

    def test_decimals(self):
        series = (Decimal(5) / 3, Decimal(35) / 6, Decimal(22) / 7)
        res = average(series)
        self.assertEqual(res, Decimal('3.547619047619047619047619047'))


class BooleanChoiceFieldCoerce(TestCase):

    def test_true_boolean(self):
        result = boolean_choice_field_coerce(True)
        self.assertTrue(result)

    def test_false_boolean(self):
        result = boolean_choice_field_coerce(False)
        self.assertFalse(result)

    def test_true_integer(self):
        result = boolean_choice_field_coerce('1')
        self.assertTrue(result)

    def test_false_integer(self):
        result = boolean_choice_field_coerce('0')
        self.assertFalse(result)

    def test_true_string(self):
        result = boolean_choice_field_coerce(1)
        self.assertTrue(result)

    def test_false_string(self):
        result = boolean_choice_field_coerce(0)
        self.assertFalse(result)


class GetModFunc(TestCase):

    def test_get_mod_func(self):
        mod_name, func_name = get_mod_func(
            'django.contrib.auth.tokens.default_token_generator')
        self.assertEqual(mod_name, 'django.contrib.auth.tokens')
        self.assertEqual(func_name, 'default_token_generator')

    def test_no_dot(self):
        mod_name, func_name = get_mod_func('django')
        self.assertEqual(mod_name, 'django')
        self.assertEqual(func_name, '')


class TimeZoneChoice(TestCase):

    def test_one_part(self):
        self.assertEqual(
            timezone_choice(u'UTC'),
            (u'UTC', u'UTC'))

    def test_two_parts(self):
        self.assertEqual(
            timezone_choice(u'Australia/Sydney'),
            (u'Australia/Sydney', u'Sydney'))

    def test_three_parts(self):
        self.assertEqual(
            timezone_choice(u'America/Indiana/Indianapolis'),
            (u'America/Indiana/Indianapolis', u'Indianapolis (Indiana)'))
