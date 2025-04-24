# -*- coding: utf-8 -*-

from django.db import migrations
from django.utils import timezone

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitemapnode",
            name="last_modified",
            field=touchtechnology.common.db.models.DateTimeField(
                default=timezone.now(), auto_now=True
            ),
            preserve_default=False,
        ),
    ]
