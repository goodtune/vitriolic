# -*- coding: utf-8 -*-

import datetime
from datetime import timezone

from django.db import migrations

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0002_article_last_modified"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="last_modified",
            field=touchtechnology.common.db.models.DateTimeField(auto_now=True),
            preserve_default=False,
        ),
    ]
