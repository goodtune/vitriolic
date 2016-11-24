# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.db.models.deletion
import touchtechnology.common.db.models
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0013_statistic_played_field'),
    ]

    operations = [
        migrations.AlterField(
            model_name='match',
            name='play_at',
            field=touchtechnology.common.db.models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, to='competition.Place', null=True),
        ),
    ]
