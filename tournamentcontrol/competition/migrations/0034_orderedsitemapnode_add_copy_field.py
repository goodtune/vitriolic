# -*- coding: utf-8 -*-

from django.db import migrations

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [("competition", "0033_matchscoresheet")]

    operations = [
        migrations.AddField(
            model_name="division",
            name="copy",
            field=touchtechnology.common.db.models.HTMLField(blank=True),
        ),
        migrations.AddField(
            model_name="place",
            name="copy",
            field=touchtechnology.common.db.models.HTMLField(blank=True),
        ),
        migrations.AddField(
            model_name="rankdivision",
            name="copy",
            field=touchtechnology.common.db.models.HTMLField(blank=True),
        ),
        migrations.AddField(
            model_name="season",
            name="copy",
            field=touchtechnology.common.db.models.HTMLField(blank=True),
        ),
        migrations.AddField(
            model_name="stage",
            name="copy",
            field=touchtechnology.common.db.models.HTMLField(blank=True),
        ),
        migrations.AddField(
            model_name="stagegroup",
            name="copy",
            field=touchtechnology.common.db.models.HTMLField(blank=True),
        ),
        migrations.AddField(
            model_name="team",
            name="copy",
            field=touchtechnology.common.db.models.HTMLField(blank=True),
        ),
    ]
