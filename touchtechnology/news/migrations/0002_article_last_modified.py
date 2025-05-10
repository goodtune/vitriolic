# -*- coding: utf-8 -*-

import datetime
from datetime import timezone

from django.db import migrations

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="last_modified",
            field=touchtechnology.common.db.models.DateTimeField(auto_now=True),
            preserve_default=False,
        ),
    ]
