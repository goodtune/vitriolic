# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import touchtechnology.common.db.models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='page',
            name='last_modified',
            field=touchtechnology.common.db.models.DateTimeField(default=timezone.now(), auto_now=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pagecontent',
            name='last_modified',
            field=touchtechnology.common.db.models.DateTimeField(default=timezone.now(), auto_now=True),
            preserve_default=False,
        ),
    ]
