from django import forms
from django.utils import timezone
from touchtechnology.common.forms.constants import TIMEZONE_CHOICES


class SelectTimezoneForm(forms.Form):
    """
    Used by touchtechnology.common.context_processors.tz to generate a
    dropdown list of timezones to be used with the TimeZone middleware and
    set-timezone view.
    """
    timezone = forms.ChoiceField(choices=TIMEZONE_CHOICES,
                                 initial=timezone.get_current_timezone)
