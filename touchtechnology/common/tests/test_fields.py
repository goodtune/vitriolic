from django.test.utils import override_settings
from test_plus import TestCase


@override_settings(ROOT_URLCONF="example_app.urls")
class DateTimeFieldTest(TestCase):
    def test_validate_form_output_tz(self):
        text = """
        <optgroup label="Australia">
            <option value="Australia/Adelaide">Adelaide</option>
            <option value="Australia/Brisbane">Brisbane</option>
            <option value="Australia/Broken_Hill">Broken Hill</option>
            <option value="Australia/Darwin">Darwin</option>
            <option value="Australia/Eucla">Eucla</option>
            <option value="Australia/Hobart">Hobart</option>
            <option value="Australia/Lindeman">Lindeman</option>
            <option value="Australia/Lord_Howe">Lord Howe</option>
            <option value="Antarctica/Macquarie">Macquarie</option>
            <option value="Australia/Melbourne">Melbourne</option>
            <option value="Australia/Perth">Perth</option>
            <option value="Australia/Sydney">Sydney</option>
        </optgroup>
        """
        with self.settings(USE_TZ=False):
            self.get("datetime:index")
            self.assertResponseNotContains(text)

        with self.settings(USE_TZ=True):
            self.get("datetime:index")
            self.assertResponseContains(text)

    def test_submit_date_time_valid(self):
        data = {
            "form-datetime_0": "1",
            "form-datetime_1": "1",
            "form-datetime_2": "2014",
            "form-datetime_3": "0",
            "form-datetime_4": "0",
            "formset-TOTAL_FORMS": "0",
            "formset-INITIAL_FORMS": "0",
            "formset-MAX_NUM_FORMS": "1000",
        }

        with self.settings(USE_TZ=False):
            self.post("datetime:index", data=data)
            self.response_302()

        data.update(
            {
                "form-datetime_5": "Australia/Sydney",
            }
        )

        with self.settings(USE_TZ=True):
            self.post("datetime:index", data=data)
            self.response_302()

    def test_submit_date_time_blank(self):
        data = {
            "form-datetime_0": "",
            "form-datetime_1": "",
            "form-datetime_2": "",
            "form-datetime_3": "",
            "form-datetime_4": "",
            "formset-TOTAL_FORMS": "0",
            "formset-INITIAL_FORMS": "0",
            "formset-MAX_NUM_FORMS": "1000",
        }

        with self.settings(USE_TZ=False):
            self.post("datetime:index", data=data)
            self.response_302()

        data.update(
            {
                "form-datetime_5": "",
            }
        )

        with self.settings(USE_TZ=True):
            self.post("datetime:index", data=data)
            self.response_302()
