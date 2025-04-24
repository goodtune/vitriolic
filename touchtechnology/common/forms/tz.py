import zoneinfo

from django import forms
from django.utils import timezone


def timezone_choice(tzname, country=None):
    """
    Given a timezone string, convert it to a two-tuple suitable
    for a choice in a FormField.

    >>> timezone_choice('UTC')
    ('UTC', 'UTC')
    >>> timezone_choice('Australia/Sydney')
    ('Australia/Sydney', 'Sydney')
    >>> timezone_choice('America/Indiana/Indianapolis')
    ('America/Indiana/Indianapolis', 'Indianapolis (Indiana)')
    """
    try:
        base, rest = tzname.split("/", 1)
    except ValueError:
        base, rest = None, tzname
    rest = rest.replace("_", " ")
    try:
        mid, rest = rest.split("/")
        if mid != base and mid != country:
            rest = "{0} ({1})".format(rest, mid)
    except ValueError:
        pass
    return (tzname, rest)


MONTH_CHOICES = (
    ("", ""),
    (1, "January"),
    (2, "February"),
    (3, "March"),
    (4, "April"),
    (5, "May"),
    (6, "June"),
    (7, "July"),
    (8, "August"),
    (9, "September"),
    (10, "October"),
    (11, "November"),
    (12, "December"),
)

DAY_CHOICES = [("", "")] + [(day, day) for day in range(1, 32)]
HOUR_CHOICES = [("", "")] + [(h, h) for h in range(24)]
MINUTE_CHOICES = [("", "")] + [(m, f"{m:02d}") for m in range(60)]
TIMEZONE_CHOICES = [
    timezone_choice(tz, tz.split("/", 1)[0])
    for tz in sorted(zoneinfo.available_timezones())
]


class SelectTimezoneForm(forms.Form):
    """
    Used by touchtechnology.common.context_processors.tz to generate a
    dropdown list of timezones to be used with the TimeZone middleware and
    set-timezone view.
    """

    timezone = forms.ChoiceField(
        choices=TIMEZONE_CHOICES, initial=timezone.get_current_timezone
    )
