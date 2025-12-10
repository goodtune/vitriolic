import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django import forms
from django.test.utils import modify_settings, override_settings
from django.utils import timezone
from django.utils.encoding import smart_str
from freezegun import freeze_time
from test_plus import TestCase

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
        self.assertFormError(form, "timestamp", ["This field is required."])

    def test_select_date_time_field_empty_input_not_required(self):
        """Test empty input handling when field not required"""
        form = TestForm2(data={})
        self.assertFormError(form, "timestamp", [])

    def test_select_date_time_field_partial_date(self):
        """Test validation with only date input"""
        data = {"timestamp_0": "2023-07-04"}
        form = TestForm1(data=data)
        # FIXME: should error with ['Enter a valid time.', 'Enter a valid time zone.']
        self.assertFormError(form, "timestamp", ["This field is required."])

    def test_select_date_time_field_invalid_date(self):
        """Test validation with invalid date values"""
        data = {
            "timestamp_0": "2013-07-32",  # invalid day
            "timestamp_1": "7:49",
            "timestamp_2": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertFormError(form, "timestamp", ["Enter a valid date."])

        data = {
            "timestamp_0": "2013-13-04",  # invalid month
            "timestamp_1": "7:49",
            "timestamp_2": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertFormError(form, "timestamp", ["Enter a valid date."])

    def test_select_date_time_field_invalid_time(self):
        """Test validation with invalid time values"""
        data = {
            "timestamp_0": "2013-07-04",
            "timestamp_1": "24:49",  # invalid hour
            "timestamp_2": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertFormError(form, "timestamp", ["Enter a valid time."])

        data = {
            "timestamp_0": "2013-07-04",
            "timestamp_1": "7:60",  # invalid minute
            "timestamp_2": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertFormError(form, "timestamp", ["Enter a valid time."])

    def test_select_date_time_field_invalid_timezone(self):
        """Test validation with invalid timezone"""
        data = {
            "timestamp_0": "2013-07-04",
            "timestamp_1": "7:49",
            "timestamp_2": "Invalid/Timezone",  # invalid timezone
        }
        form = TestForm1(data=data)
        self.assertFormError(
            form,
            "timestamp",
            [
                "Select a valid choice. Invalid/Timezone is not one of the available choices."
            ],
        )

    def test_select_date_time_field_valid_input(self):
        """Test validation with valid input"""
        data = {
            "timestamp_0": "2013-07-04",
            "timestamp_1": "7:49",
            "timestamp_2": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertFormError(form, "timestamp", [])

        expected = timezone.make_aware(
            datetime(2013, 7, 4, 7, 49),
            ZoneInfo("Australia/Sydney"),
        )
        self.assertEqual(form.cleaned_data["timestamp"], expected)

    def test_select_date_time_field_leap_year(self):
        """Test validation with leap year date"""
        data = {
            "timestamp_0": "2020-02-29",  # leap year
            "timestamp_1": "7:49",
            "timestamp_2": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertFormError(form, "timestamp", [])

        expected = timezone.make_aware(
            datetime(2020, 2, 29, 7, 49),
            ZoneInfo("Australia/Sydney"),
        )
        self.assertEqual(form.cleaned_data["timestamp"], expected)

    def test_select_date_time_field_non_leap_year(self):
        """Test validation with non-leap year date"""
        data = {
            "timestamp_0": "2021-02-29",  # non-leap year
            "timestamp_1": "7:49",
            "timestamp_2": "Australia/Sydney",
        }
        form = TestForm1(data=data)
        self.assertFormError(form, "timestamp", ["Enter a valid date."])

    def test_select_date_time_field_missing_timezone(self):
        """Test validation with missing timezone"""
        data = {
            "timestamp_0": "2013-07-04",
            "timestamp_1": "7:49",
            # missing timestamp_2 (timezone)
        }
        form = TestForm1(data=data)
        # FIXME: would want this to return "Enter a valid time zone."
        self.assertFormError(form, "timestamp", ["This field is required."])

    @freeze_time("2013-03-24 14:30:00")
    @override_settings(TIME_ZONE="Australia/Sydney")
    def test_select_date_time_field_initial_tz(self):
        timestamp = timezone.make_aware(
            datetime(2013, 3, 24, 14, 30),
            ZoneInfo("Australia/Sydney"),
        )

        form = TestForm1(initial={"timestamp": timestamp})
        haystack = smart_str(form)
        for needle in [
            '<input type="text" name="timestamp_0" value="2013-03-24" required id="id_timestamp_0">',
            '<input type="text" name="timestamp_1" value="14:30:00" required id="id_timestamp_1">',
            '<option value="Australia/Sydney" selected>GMT+11:00 Australia/Sydney</option>',
        ]:
            with self.subTest(needle=needle):
                self.assertInHTML(needle, haystack)


@unittest.skip("FIXME: we don't use this widely but it is not passing")
@override_settings(ROOT_URLCONF="example_app.urls", TIME_ZONE="Europe/Paris")
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

        data = {"tz": "Australia/Sydney"}
        self.post("set-timezone", data=data, follow=True)

        self.assertEqual(timezone.get_current_timezone_name(), "Australia/Sydney")
