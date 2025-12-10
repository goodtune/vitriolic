from django.test.utils import override_settings
from freezegun import freeze_time
from test_plus import TestCase


@override_settings(ROOT_URLCONF="example_app.urls")
class DateTimeFieldTest(TestCase):
    @freeze_time("2014-07-01")
    def test_validate_form_output_tz(self):
        self.get("datetime:index")
        self.assertResponseContains(
            '<option value="Australia/Sydney">GMT+10:00 Australia/Sydney</option>'
        )

    def test_submit_date_time_valid(self):
        data = {
            "form-datetime_0": "2014-1-1",
            "form-datetime_1": "0:00",
            "form-datetime_2": "Australia/Sydney",
            "formset-TOTAL_FORMS": "0",
            "formset-INITIAL_FORMS": "0",
            "formset-MAX_NUM_FORMS": "1000",
        }
        self.post("datetime:index", data=data)
        self.response_302()

    def test_submit_date_time_blank(self):
        data = {
            "form-datetime_0": "",
            "form-datetime_1": "",
            "form-datetime_2": "",
            "formset-TOTAL_FORMS": "0",
            "formset-INITIAL_FORMS": "0",
            "formset-MAX_NUM_FORMS": "1000",
        }
        self.post("datetime:index", data=data)
        self.response_302()
