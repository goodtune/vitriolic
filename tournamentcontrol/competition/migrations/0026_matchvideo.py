# -*- coding: utf-8 -*-

import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0025_matchvideo_baseline"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="videos",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.URLField(), null=True, size=None
            ),
        ),
        migrations.AlterField(
            model_name="matchvideo",
            name="match",
            field=touchtechnology.common.db.models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="competition.Match"
            ),
        ),
    ]
