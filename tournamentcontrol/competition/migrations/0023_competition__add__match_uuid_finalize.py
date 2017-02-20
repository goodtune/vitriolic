# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0023_competition__add__match_uuid_data'),
    ]

    operations = [
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
