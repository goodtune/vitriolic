# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import uuid


def initial_uuid(apps, schema_editor):
    Match = apps.get_model('competition', 'Match')

    for m in Match.objects.select_related('stage__division'):
        m.uuid = uuid.UUID(
            '{00000000-%04x-%04x-%04x-000000000000}' % (
                m.stage.division.pk, m.stage.pk, m.pk))
        m.save()


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0022_competition__remove__person_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='match',
            name='uuid',
            field=models.UUIDField(
                null=True,
                editable=False,
                unique=True,
                db_index=True,
            ),
        ),

        migrations.RunPython(
            initial_uuid, reverse_code=migrations.RunPython.noop),

        migrations.AlterField(
            model_name='match',
            name='uuid',
            field=models.UUIDField(
                unique=True,
                editable=False,
                db_index=True,
            ),
        ),

        migrations.RunSQL(
            "SELECT 1;",
            "SELECT 1;",
            state_operations=[
                migrations.AlterField(
                    model_name='match',
                    name='uuid',
                    field=models.UUIDField(
                        default=uuid.uuid4,
                        unique=True,
                        editable=False,
                        db_index=True,
                    ),
                ),
            ],
        ),

    ]
