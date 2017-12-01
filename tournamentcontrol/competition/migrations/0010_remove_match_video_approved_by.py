# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0009_remove_byeteam'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='matchvideo',
            options={'verbose_name': 'video'},
        ),
        migrations.RemoveField(
            model_name='matchvideo',
            name='approved_by',
        ),
        migrations.AlterField(
            model_name='matchvideo',
            name='url',
            field=models.URLField(max_length=255, verbose_name='URL'),
            preserve_default=True,
        ),
    ]
