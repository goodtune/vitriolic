# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


def set_zero_to_none(apps, schema_editor):
    SimpleScoreMatchStatistic = apps.get_model(
        "competition", "SimpleScoreMatchStatistic")
    SimpleScoreMatchStatistic.objects.filter(mvp=0) \
                                     .update(mvp=None)
    SimpleScoreMatchStatistic.objects.filter(points=0) \
                                     .update(points=None)


def set_none_to_zero(apps, schema_editor):
    SimpleScoreMatchStatistic = apps.get_model(
        "competition", "SimpleScoreMatchStatistic")
    SimpleScoreMatchStatistic.objects.filter(mvp__isnull=True) \
                                     .update(mvp=0)
    SimpleScoreMatchStatistic.objects.filter(points__isnull=True) \
                                     .update(points=0)


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0007_match_videos'),
    ]

    operations = [
        migrations.AlterField(
            model_name='simplescorematchstatistic',
            name='mvp',
            field=models.SmallIntegerField(null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='simplescorematchstatistic',
            name='points',
            field=models.SmallIntegerField(null=True, blank=True),
            preserve_default=True,
        ),
        migrations.RunPython(set_zero_to_none, set_none_to_zero),
    ]
