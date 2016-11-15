# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime
import touchtechnology.common.db.models
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='last_modified',
            field=touchtechnology.common.db.models.DateTimeField(default=datetime.datetime(2015, 3, 23, 11, 10, 25, 290897, tzinfo=utc), auto_now=True),
            preserve_default=False,
        ),
    ]
