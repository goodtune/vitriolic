# -*- coding: utf-8 -*-

from django.db import migrations
from django.utils import timezone

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="page",
            name="last_modified",
            field=touchtechnology.common.db.models.DateTimeField(
                default=timezone.now(), auto_now=True
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="pagecontent",
            name="last_modified",
            field=touchtechnology.common.db.models.DateTimeField(
                default=timezone.now(), auto_now=True
            ),
            preserve_default=False,
        ),
    ]
