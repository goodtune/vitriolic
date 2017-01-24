# coding=UTF-8

from datetime import date, datetime, time

import pytz
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone
from touchtechnology.common.forms import (
    BooleanChoiceField, EmailField, HTMLField, SelectDateField,
    SelectDateTimeField, SelectTimeField, iCheckSelectMultiple,
    permissionformset_factory,
)
from touchtechnology.common.models import SitemapNode
from touchtechnology.common.tests import factories


class CustomFormField(TestCase):

    def test_email_field(self):
        self.assertFieldOutput(
            EmailField,
            {'a@a.com': 'a@a.com', 'B@B.COM': 'b@b.com'},
            {'aaa': [u'Enter a valid email address.']})
        self.assertFieldOutput(
            EmailField,
            {'a@a.com': 'a@a.com', 'B@B.COM': 'B@B.COM'},
            {'aaa': [u'Enter a valid email address.']},
            (),
            {'lowercase': False})

    def test_html_field(self):
        valid = {
            u'sauté': 'saut&#233;',
        }
        self.assertFieldOutput(HTMLField, valid, {})

    def test_boolean_choice_field(self):
        valid = {
            u'0': False,
            u'1': True,
        }
        self.assertFieldOutput(BooleanChoiceField, valid, {})

    def test_select_date_field(self):
        valid = {
            ('25', '9', '2013'): date(2013, 9, 25),
        }
        invalid = {
            ('30', '2', '2013'): [u'Please enter a valid date.'],
        }
        self.assertFieldOutput(SelectDateField, valid, invalid,
                               empty_value=None)

    def test_select_time_field(self):
        valid = {
            ('10', '15'): time(10, 15),
            ('15', '15'): time(15, 15),
        }
        invalid = {
            ('42', '0'): [u'Hour must be in 0..23'],
            ('1', '72'): [u'Minute must be in 0..59'],
            ('', '15'): [u'Hour must be in 0..23'],
            ('10', ''): [u'Minute must be in 0..59'],
        }
        self.assertFieldOutput(SelectTimeField, valid, invalid,
                               empty_value=None)

    def test_select_time_field_advanced(self):
        "Ensure that 'empty' input behaves correctly when required is toggled."
        input = ('', '')

        # If the field is required, we expect a validation error to be raised.
        required = SelectTimeField(required=True)
        with self.assertRaises(ValidationError):
            required.clean(input)

        # If the field is optional, we expect None to be returned.
        optional = SelectTimeField(required=False)
        self.assertEqual(optional.clean(input), None)

    @override_settings(USE_TZ=False)
    def test_select_date_time_field(self):
        valid = {
            ('25', '9', '2013', '10', '15'): datetime(2013, 9, 25, 10, 15),
        }
        self.assertFieldOutput(SelectDateTimeField, valid, {},
                               empty_value=None)

    @override_settings(USE_TZ=True)
    def test_select_date_time_field_tz(self):
        est = pytz.timezone('Australia/Sydney')
        utc_dt = datetime(2013, 9, 25, 10, 15, tzinfo=timezone.utc)
        est_dt = datetime(2013, 9, 25, 10, 15, tzinfo=est)
        valid = {
            ('25', '9', '2013', '10', '15', 'UTC'): utc_dt,
            ('25', '9', '2013', '10', '15', 'Australia/Sydney'): est_dt,
        }
        invalid = {
            ('25', '9', '2013', '10', '15'): [u'Please select a time zone.'],
            ('25', '9', '2013', '10', '15', ''): [u'Please select a valid '
                                                  u'time zone.'],
        }
        self.assertFieldOutput(SelectDateTimeField, valid, invalid,
                               empty_value=None)


class TestPermissionFormSet(TestCase):

    def setUp(self):
        self.UserModel = get_user_model()
        self.queryset = (
            Permission.objects
            .filter(content_type=ContentType.objects.get_for_model(
                SitemapNode
            ))
            .exclude(codename__startswith='add_')
        )
        self.instance = SitemapNode.objects.create(title='permissions')
        self.staff = factories.UserFactory.create(
            is_staff=True, is_superuser=True)
        self.regular = factories.UserFactory.create()

    def test_staff_only(self):
        formset_class = permissionformset_factory(
            SitemapNode, staff_only=True)
        formset = formset_class(queryset=self.queryset, instance=self.instance)
        self.assertQuerysetEqual(
            formset.forms[0].fields['users'].queryset,
            map(repr, self.UserModel.objects.filter(is_staff=True)),
        )

    def test_all_users(self):
        formset_class = permissionformset_factory(
            SitemapNode, staff_only=False)
        formset = formset_class(queryset=self.queryset, instance=self.instance)
        self.assertQuerysetEqual(
            formset.forms[0].fields['users'].queryset.order_by('pk'),
            map(repr, self.UserModel.objects.order_by('pk')),
        )

    def test_user_widget_checkbox_lte(self):
        "Less than equal to 5 users, should be iCheckboxSelectMultiple widget"
        formset_class = permissionformset_factory(
            SitemapNode, staff_only=False, max_checkboxes=5)
        formset = formset_class(queryset=self.queryset, instance=self.instance)
        self.assertEqual(
            formset.forms[0].fields['users'].queryset.count(),
            3,  # need to account for the AnonymousUser that guardian creates
        )
        self.assertIsInstance(
            formset.forms[0].fields['users'].widget,
            iCheckSelectMultiple,
        )

    def test_user_widget_checkbox_eq(self):
        "Equal to 3 users, should be iCheckboxSelectMultiple widget"
        formset_class = permissionformset_factory(
            SitemapNode, staff_only=False, max_checkboxes=3)
        formset = formset_class(queryset=self.queryset, instance=self.instance)
        self.assertEqual(
            formset.forms[0].fields['users'].queryset.count(),
            3,  # need to account for the AnonymousUser that guardian creates
        )
        self.assertIsInstance(
            formset.forms[0].fields['users'].widget,
            iCheckSelectMultiple,
        )

    def test_user_widget_select2(self):
        "More than 1 user, should not be iCheckboxSelectMultiple widget"
        formset_class = permissionformset_factory(
            SitemapNode, staff_only=False, max_checkboxes=1)
        formset = formset_class(queryset=self.queryset, instance=self.instance)
        self.assertEqual(
            formset.forms[0].fields['users'].queryset.count(),
            3,  # need to account for the AnonymousUser that guardian creates
        )
        self.assertNotIsInstance(
            formset.forms[0].fields['users'].widget,
            iCheckSelectMultiple,
        )
