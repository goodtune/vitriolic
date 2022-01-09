from __future__ import unicode_literals

from operator import itemgetter

import pytz
from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


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


def timezone_choices(countries, timezones, key):
    yield "", ""
    for iso3166, country in sorted(countries.items(), key=key):
        zones = timezones.get(iso3166, [])
        zones = [timezone_choice(zone, country) for zone in zones]
        zones.sort(key=key)
        yield country, zones


DAY_CHOICES = [("", "")] + list(zip(*[range(1, 32)] * 2))

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

HOUR_CHOICES = [("", "")] + list(zip(*[range(0, 24, 1)] * 2))

MINUTES = range(0, 60)

MINUTE_CHOICES = [("", "")] + list(zip(MINUTES, ["%02d" % m for m in MINUTES]))

TIMEZONE_CHOICES = list(
    timezone_choices(pytz.country_names, pytz.country_timezones, itemgetter(1))
)

# Add UTC and MGT
TIMEZONE_CHOICES.insert(
    1,
    (
        _("Universal"),
        [
            ("UTC", _("Coordinated Universal Time")),
            ("GMT", _("Greenwich Mean Time")),
        ],
    ),
)


class SelectTimezoneForm(forms.Form):
    """
    Used by touchtechnology.common.context_processors.tz to generate a
    dropdown list of timezones to be used with the TimeZone middleware and
    set-timezone view.
    """

    timezone = forms.ChoiceField(
        choices=TIMEZONE_CHOICES, initial=timezone.get_current_timezone
    )
