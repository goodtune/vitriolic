from datetime import datetime
from os.path import dirname, join
from unittest import skipIf

from django import VERSION
from django.test.utils import modify_settings, override_settings
from django.utils import timezone
from django.utils.encoding import smart_str
from test_plus import TestCase

from touchtechnology.common.tests.test_timezone_forms import TestForm1


class TimeZoneTests(TestCase):
    maxDiff = None

    def get_html(self, filename):
        with open(join(dirname(__file__), "test_html", filename)) as fp:
            html = fp.read()
        return smart_str(html)

    @override_settings(TIME_ZONE="Australia/Sydney")
    def test_select_date_time_field_empty_tz(self):
        data = {
            "timestamp_0": "4",
            "timestamp_1": "7",
            "timestamp_2": "2013",
            "timestamp_3": "",
            "timestamp_4": "",
            "timestamp_5": "Europe/London",
        }

        # with only date fields completed validation should fail
        form = TestForm1(data=data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors["timestamp"], ["Please enter a valid date and time."]
        )

        data.update({"timestamp_3": "7", "timestamp_4": "49"})

        # time fields added should allow validation to succeed
        form = TestForm1(data=data)
        self.assertTrue(form.is_valid())

        # verify the cleaned value from user input is a datetime
        # object as we would expect it.
        timestamp = form.cleaned_data.get("timestamp")
        self.assertEqual(
            datetime(2013, 7, 4, 16, 49),
            timezone.make_naive(timestamp, timezone.get_current_timezone()),
        )

    @skipIf(VERSION < (4, 1), "Django < 4.1")
    @override_settings(TIME_ZONE="Australia/Sydney")
    def test_select_date_time_field_initial_tz(self):
        timestamp = timezone.make_aware(
            datetime(2013, 3, 24, 14, 30), timezone.get_current_timezone()
        )

        initial = {
            "timestamp": timestamp,
        }
        form = TestForm1(initial=initial)

        # check that the HTML output is as expected for a naked
        # form renderer.
        html1 = smart_str(form)
        html2 = self.get_html("select_date_time_field_initial_tz.html")
        self.assertHTMLEqual(html1, html2)


@override_settings(ROOT_URLCONF="example_app.urls")
@modify_settings(
    MIDDLEWARE={"append": "touchtechnology.common.middleware.timezone_middleware"}
)
class TestTimezoneMiddleware(TestCase):
    def test_set_timezone(self):
        "Ensure time zone is correct before, during and after a set request"
        self.assertEqual(
            timezone.get_current_timezone_name(), timezone.get_default_timezone_name()
        )

        data = {
            "timezone": "Australia/Sydney",
        }
        self.post("set-timezone", data=data, follow=True)
        self.assertResponseContains(
            '<option value="Australia/Sydney" selected>Sydney</option>'
        )

        self.assertEqual(
            timezone.get_current_timezone_name(), timezone.get_default_timezone_name()
        )
