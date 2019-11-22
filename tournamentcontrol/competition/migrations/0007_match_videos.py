# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.db.models.deletion
import touchtechnology.common.db.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("competition", "0006_sportingpulse_import_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="MatchVideo",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                ("url", models.URLField(max_length=255)),
                (
                    "approved_by",
                    touchtechnology.common.db.models.ForeignKey(
                        blank=True,
                        to=settings.AUTH_USER_MODEL,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                    ),
                ),
                (
                    "match",
                    touchtechnology.common.db.models.ForeignKey(
                        related_name="videos",
                        to="competition.Match",
                        on_delete=django.db.models.deletion.PROTECT,
                    ),
                ),
            ],
            options={},
            bases=(models.Model,),
        ),
    ]
