from datetime import datetime
from pathlib import Path
import unittest

from django import forms
from django.test.utils import modify_settings, override_settings
from django.utils import timezone
from django.utils.encoding import smart_str
from test_plus import TestCase
from zoneinfo import ZoneInfo

from touchtechnology.common.forms.fields import SelectDateTimeField


class TestForm1(forms.Form):
    timestamp = SelectDateTimeField()


class TestForm2(forms.Form):
    timestamp = SelectDateTimeField(required=False)


class TimeZoneTests(TestCase):
    def get_html(self, filename):
        with open(Path(__file__).parent / "test_html" / filename) as fp:
            html = fp.read()
        return smart_str(html)

    def test_select_date_time_field_empty_input(self):
        """Test empty input handling"""
        form = TestForm1(data={})
        self.assertFalse(form.is_valid())
        self.assertFormError(form, "timestamp", ["This field is required."])

    def test_select_date_time_field_empty_input_not_required(self):
        """Test empty input handling when field not required"""
        form = TestForm2(data={})
        # self.assertTrue(form.is_valid())
        self.assertFormError(form, "timestamp", [])

    def test_select_date_time_field_partial_date(self):
        """Test validation with partial date input"""
        data = {
            "timestamp_0": "4",  # day
            "timestamp_1": "7",  # month
            "timestamp_2": "2013",  # year
        }
        form = TestForm1(data=data)
        self.assertFalse(form.is_valid())
        self.assertFormError(form, "timestamp", ["Please enter a valid date and time."])

    def test_select_date_time_field_invalid_date(self):
        """Test validation with invalid date values"""
        # Invalid day
        data = {
            "timestamp_0": "32",  # invalid day
            "timestamp_1": "7",
            "timestamp_2": "2013",
            "timestamp_3": "7",
            "timestamp_4": "49",
            "timestamp_5": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertFalse(form.is_valid())
        self.assertFormError(form, "timestamp", ["Please enter a valid date and time."])

        # Invalid month
        data = {
            "timestamp_0": "4",
            "timestamp_1": "13",  # invalid month
            "timestamp_2": "2013",
            "timestamp_3": "7",
            "timestamp_4": "49",
            "timestamp_5": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertFalse(form.is_valid())
        self.assertFormError(form, "timestamp", ["Please enter a valid date and time."])

    def test_select_date_time_field_invalid_time(self):
        """Test validation with invalid time values"""
        # Invalid hour
        data = {
            "timestamp_0": "4",
            "timestamp_1": "7",
            "timestamp_2": "2013",
            "timestamp_3": "24",  # invalid hour
            "timestamp_4": "49",
            "timestamp_5": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertFalse(form.is_valid())
        self.assertFormError(form, "timestamp", ["Please enter a valid date and time."])

        # Invalid minute
        data = {
            "timestamp_0": "4",
            "timestamp_1": "7",
            "timestamp_2": "2013",
            "timestamp_3": "7",
            "timestamp_4": "60",  # invalid minute
            "timestamp_5": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertFalse(form.is_valid())
        self.assertFormError(form, "timestamp", ["Please enter a valid date and time."])

    def test_select_date_time_field_invalid_timezone(self):
        """Test validation with invalid timezone"""
        data = {
            "timestamp_0": "4",
            "timestamp_1": "7",
            "timestamp_2": "2013",
            "timestamp_3": "7",
            "timestamp_4": "49",
            "timestamp_5": "Invalid/Timezone",  # invalid timezone
        }
        form = TestForm1(data=data)
        self.assertFalse(form.is_valid())
        self.assertFormError(
            form, "timestamp", ["No time zone found with key Invalid/Timezone"]
        )

    def test_select_date_time_field_valid_input(self):
        """Test validation with valid input"""
        data = {
            "timestamp_0": "4",
            "timestamp_1": "7",
            "timestamp_2": "2013",
            "timestamp_3": "7",
            "timestamp_4": "49",
            "timestamp_5": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertTrue(form.is_valid())
        timestamp = form.cleaned_data.get("timestamp")
        expected = timezone.make_aware(
            datetime(2013, 7, 4, 7, 49),
            ZoneInfo("Australia/Sydney"),
        )
        self.assertEqual(expected, timestamp)

    def test_select_date_time_field_leap_year(self):
        """Test validation with leap year date"""
        data = {
            "timestamp_0": "29",
            "timestamp_1": "2",
            "timestamp_2": "2020",  # leap year
            "timestamp_3": "7",
            "timestamp_4": "49",
            "timestamp_5": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertTrue(form.is_valid())
        timestamp = form.cleaned_data.get("timestamp")
        expected = timezone.make_aware(
            datetime(2020, 2, 29, 7, 49),
            ZoneInfo("Australia/Sydney"),
        )
        self.assertEqual(expected, timestamp)

    def test_select_date_time_field_non_leap_year(self):
        """Test validation with non-leap year date"""
        data = {
            "timestamp_0": "29",
            "timestamp_1": "2",
            "timestamp_2": "2021",  # non-leap year
            "timestamp_3": "7",
            "timestamp_4": "49",
            "timestamp_5": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertFalse(form.is_valid())
        self.assertFormError(form, "timestamp", ["Please enter a valid date and time."])

    @override_settings(TIME_ZONE="Australia/Sydney")
    def test_select_date_time_field_initial_tz(self):
        timestamp = timezone.make_aware(
            datetime(2013, 3, 24, 14, 30),
            ZoneInfo("Australia/Sydney"),
        )

        form = TestForm1(initial={"timestamp": timestamp})
        haystack = smart_str(form)
        needle = self.get_html("select_date_time_field_initial_tz.html")
        self.assertInHTML(needle, haystack)


@override_settings(ROOT_URLCONF="example_app.urls")
@modify_settings(
    MIDDLEWARE={"append": "touchtechnology.common.middleware.timezone_middleware"}
)
class TestTimezoneMiddleware(TestCase):
    def test_set_timezone(self):
        "Ensure time zone is correct before, during and after a set request"
        self.assertEqual(
            timezone.get_current_timezone_name(),
            timezone.get_default_timezone_name(),
        )

        data = {"timezone": "Australia/Sydney"}
        self.post("set-timezone", data=data, follow=True)

        self.assertResponseContains(
            '<option value="Australia/Sydney" selected>Sydney</option>'
        )

        self.assertEqual(
            timezone.get_current_timezone_name(),
            timezone.get_default_timezone_name(),
        )
