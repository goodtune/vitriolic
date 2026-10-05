from dateutil.rrule import DAILY, WEEKLY
from django.db import models
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


class LiveStreamPrivacy(models.TextChoices):
    PUBLIC = "public", _("Public")
    PRIVATE = "private", _("Private")
    UNLISTED = "unlisted", _("Unlisted")


class ClubStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    INACTIVE = "inactive", _("Inactive")
    HIDDEN = "hidden", _("Hidden")
