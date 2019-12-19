# -*- coding: utf-8 -*-

import datetime

from django.db import migrations
from django.utils.timezone import utc

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0002_article_last_modified"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="last_modified",
            field=touchtechnology.common.db.models.DateTimeField(
                default=datetime.datetime(2015, 3, 23, 11, 11, 17, 201480, tzinfo=utc),
                auto_now=True,
            ),
            preserve_default=False,
        ),
    ]
