# -*- coding: utf-8 -*-

import django.db.models.deletion
from django.db import migrations

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0013_statistic_played_field"),
    ]

    operations = [
        migrations.AlterField(
            model_name="match",
            name="play_at",
            field=touchtechnology.common.db.models.ForeignKey(
                on_delete=django.db.models.deletion.SET_NULL,
                blank=True,
                to="competition.Place",
                null=True,
            ),
        ),
    ]
