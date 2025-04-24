# -*- coding: utf-8 -*-

from django.db import migrations

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0029_seasonreferee"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="seasonreferee",
            options={
                "ordering": (
                    "club",
                    "season",
                    "person__last_name",
                    "person__first_name",
                ),
                "verbose_name": "referee",
            },
        ),
        migrations.AddField(
            model_name="match",
            name="referees",
            field=touchtechnology.common.db.models.ManyToManyField(
                blank=True, related_name="matches", to="competition.SeasonReferee"
            ),
        ),
    ]
