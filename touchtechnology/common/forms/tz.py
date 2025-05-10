from django import forms
from timezone_field import TimeZoneFormField


class SelectTimezoneForm(forms.Form):
    tz = TimeZoneFormField(use_pytz=False, choices_display="WITH_GMT_OFFSET")
