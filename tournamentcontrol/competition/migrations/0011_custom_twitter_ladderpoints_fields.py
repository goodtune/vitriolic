# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import tournamentcontrol.competition.models
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0010_remove_match_video_approved_by'),
    ]

    operations = [
        migrations.AlterField(
            model_name='club',
            name='twitter',
            field=tournamentcontrol.competition.models.TwitterField(
                help_text='Official Twitter name for use in social "mentions"',
                max_length=50,
                blank=True,
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='division',
            name='points_formula',
            field=tournamentcontrol.competition.models.LadderPointsField(
                null=True,
                verbose_name='Points system',
                blank=True,
            ),
            preserve_default=True,
        ),
    ]
