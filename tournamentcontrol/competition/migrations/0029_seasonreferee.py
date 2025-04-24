# -*- coding: utf-8 -*-

import django.db.models.deletion
from django.db import migrations, models

import touchtechnology.common.db.models
import tournamentcontrol.competition.models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0028_drop_matchvideo"),
    ]

    operations = [
        migrations.CreateModel(
            name="SeasonReferee",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
            ],
            options={
                "ordering": (
                    "club",
                    "season",
                    "person__last_name",
                    "person__first_name",
                ),
            },
            bases=(tournamentcontrol.competition.models.AdminUrlMixin, models.Model),
        ),
        migrations.AddField(
            model_name="seasonreferee",
            name="club",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="referees",
                to="competition.Club",
            ),
        ),
        migrations.AddField(
            model_name="seasonreferee",
            name="person",
            field=touchtechnology.common.db.models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to="competition.Person"
            ),
        ),
        migrations.AddField(
            model_name="seasonreferee",
            name="season",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="referees",
                to="competition.Season",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="seasonreferee",
            unique_together=set([("season", "person")]),
        ),
    ]
