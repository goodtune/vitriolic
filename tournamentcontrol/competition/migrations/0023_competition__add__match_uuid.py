# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


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

    ]
