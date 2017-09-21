from operator import itemgetter

import pytz
from django.utils.translation import ugettext_lazy as _
from touchtechnology.common.utils import timezone_choices

DAY_CHOICES = [('', '')] + list(zip(*[range(1, 32)] * 2))

MONTH_CHOICES = (
    ('', ''),
    (1, 'January'),
    (2, 'February'),
    (3, 'March'),
    (4, 'April'),
    (5, 'May'),
    (6, 'June'),
    (7, 'July'),
    (8, 'August'),
    (9, 'September'),
    (10, 'October'),
    (11, 'November'),
    (12, 'December'),
)

HOUR_CHOICES = [('', '')] + list(zip(*[range(0, 24, 1)] * 2))

MINUTES = range(0, 60)

MINUTE_CHOICES = [('', '')] + list(zip(MINUTES, ['%02d' % m for m in MINUTES]))

TIMEZONE_CHOICES = list(timezone_choices(
    pytz.country_names, pytz.country_timezones, itemgetter(1)))

# Add UTC and MGT
TIMEZONE_CHOICES.insert(1, (_('Universal'), [
    ('UTC', _("Coordinated Universal Time")),
    ('GMT', _("Greenwich Mean Time")),
]))
