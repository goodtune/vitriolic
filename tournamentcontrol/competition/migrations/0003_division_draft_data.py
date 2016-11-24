# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def set_draft_false(apps, schema_editor):
    Division = apps.get_model("competition", "Division")
    Division.objects.update(draft=False)


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0002_division_draft'),
    ]

    operations = [
        migrations.RunPython(set_draft_false, set_draft_false),
    ]
