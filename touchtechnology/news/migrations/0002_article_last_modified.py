# -*- coding: utf-8 -*-

import datetime

from django.db import migrations
from django.utils.timezone import utc

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="last_modified",
            field=touchtechnology.common.db.models.DateTimeField(
                default=datetime.datetime(2015, 3, 23, 11, 10, 25, 290897, tzinfo=utc),
                auto_now=True,
            ),
            preserve_default=False,
        ),
    ]
