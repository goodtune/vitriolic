from django.db import models
from django.utils.translation import gettext_lazy as _


class HighlightTemplateType(models.TextChoices):
    MATCH_SCORE = "match_score", _("Match score")
    GROUND_DAY = "ground_day", _("Ground day schedule")
    TEAM_SCHEDULE = "team_schedule", _("Team schedule")
