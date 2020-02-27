import pytz
from dateutil.rrule import DAILY, WEEKLY
from django.utils.translation import gettext_lazy as _

GENDER_CHOICES = (
    ("M", _("Male")),
    ("F", _("Female")),
    ("X", _("Unspecified")),
)

SEASON_MODE_CHOICES = (
    (WEEKLY, _("Season")),
    (DAILY, _("Tournament")),
)

WIN_LOSE = {
    "W": _("Winner"),
    "L": _("Loser"),
}

TIMELINE_TYPE_CHOICES = (
    ('TIME', _('Timing Event')),
    ('SCORE', _('Scoring Event')),
    ('DISCIPLINE', _('Discipline Event'))
)

TIMELINE_TIME_CHOICES = (
    ('START', _('Started')),
    (
        _('Break in play'),
        ('QUARTER', _('Quarter break')),
        ('HALF', _('Half-time break')),
        ('PERIOD', _('Period break')),
        ('BREAK', _('Break')),
        ('RESUME', _('Play resumed')),
    ),
    ('FINISH', _('Completed')),
)

TIMELINE_SCORE_CHOICES = (
    ('HOME', _('Home team')),
    ('AWAY', _('Away team')),
)

###################
# TIME ZONE NAMES #
###################

"""
Ideally this would be a better list for the specific uses of the site in
question. For example, it is perhaps much easier to list just the Australian
time zones for sites deployed for Australian customers.

This is also implemented in touchtechnology.common.forms and should probably
be moved and better leveraged in future release.

See https://bitbucket.org/touchtechnology/common/issue/16/
"""


PYTZ_TIME_ZONE_CHOICES = [("\x20Standard", (("UTC", "UTC"), ("GMT", "GMT")))]
for iso, name in pytz.country_names.items():
    values = sorted(pytz.country_timezones.get(iso, []))
    names = [s.rsplit("/", 1)[1].replace("_", " ") for s in values]
    PYTZ_TIME_ZONE_CHOICES.append((name, [each for each in zip(values, names)]))
PYTZ_TIME_ZONE_CHOICES.sort()
