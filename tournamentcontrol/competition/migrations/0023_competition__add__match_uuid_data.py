# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import uuid

from django.db import migrations


def initial_uuid(apps, schema_editor):
    Match = apps.get_model('competition', 'Match')

    for m in Match.objects.select_related('stage__division'):
        m.uuid = uuid.UUID(
            '{00000000-%04x-%04x-%04x-000000000000}' % (
                m.stage.division.pk, m.stage.pk, m.pk))
        m.save()


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0023_competition__add__match_uuid'),
    ]

    operations = [
        migrations.RunPython(
            initial_uuid, reverse_code=migrations.RunPython.noop),

    ]
