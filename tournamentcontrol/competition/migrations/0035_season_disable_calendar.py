# -*- coding: utf-8 -*-
# Generated by Django 1.11.25 on 2019-10-31 12:32
from __future__ import unicode_literals

import touchtechnology.common.db.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0034_orderedsitemapnode_add_copy_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="season",
            name="disable_calendar",
            field=touchtechnology.common.db.models.BooleanField(
                default=False,
                help_text=(
                    "Set to prevent the iCalendar feature for this season. "
                    "Will hide icon in front-end and disable functionality. "
                    "Batch process may disable after last match of tournament "
                    "has taken place."
                ),
            ),
        ),
    ]
