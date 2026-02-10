"""Compat layer exposing common field classes for historical migrations."""

from django.db.models import *  # noqa: F401,F403

from touchtechnology.common import fields as tt_fields

# Re-export custom field implementations expected by migrations.
BooleanField = tt_fields.BooleanField
DateField = tt_fields.DateField
DateTimeField = tt_fields.DateTimeField
EmailField = tt_fields.EmailField
HTMLField = tt_fields.HTMLField
LocationField = tt_fields.LocationField
ManyToManyField = tt_fields.ManyToManyField
TemplatePathField = tt_fields.TemplatePathField
TimeField = tt_fields.TimeField
