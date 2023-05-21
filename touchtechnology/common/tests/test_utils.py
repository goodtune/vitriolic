from unittest import mock
from test_plus import TestCase
from touchtechnology.common.forms.fields import boolean_choice_field_coerce
from touchtechnology.common.forms.tz import timezone_choice
from touchtechnology.common.utils import get_base_url, get_mod_func


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
        self.assertEqual(timezone_choice("UTC"), ("UTC", "UTC"))

    def test_two_parts(self):
        self.assertEqual(
            timezone_choice("Australia/Sydney"), ("Australia/Sydney", "Sydney")
        )

    def test_three_parts(self):
        self.assertEqual(
            timezone_choice("America/Indiana/Indianapolis"),
            ("America/Indiana/Indianapolis", "Indianapolis (Indiana)"),
        )


class GetBaseUrl(TestCase):

    @mock.patch('touchtechnology.common.utils.connection')
    def test_tenant_no_prepend_www(self, connection):
        connection.tenant = mock.Mock(['domain_url'])
        connection.tenant.domain_url = 'example.com'
        self.assertEqual('http://example.com/', get_base_url())

    @mock.patch('touchtechnology.common.utils.connection')
    def test_tenant_prepend_www_true(self, connection):
        connection.tenant = mock.Mock(['domain_url', 'prepend_www'])
        connection.tenant.domain_url = 'example.com'
        connection.tenant.prepend_www = True
        self.assertEqual('http://www.example.com/', get_base_url())

    @mock.patch('touchtechnology.common.utils.connection')
    def test_tenant_prepend_www_false(self, connection):
        connection.tenant = mock.Mock(['domain_url', 'prepend_www'])
        connection.tenant.domain_url = 'example.com'
        connection.tenant.prepend_www = False
        self.assertEqual('http://example.com/', get_base_url())

    def test_site(self):
        self.assertEqual('http://example.com/', get_base_url())
