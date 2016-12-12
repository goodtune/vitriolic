# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0004_alter_person_gender'),
    ]

    operations = [
        migrations.AddField(
            model_name='club',
            name='facebook',
            field=models.URLField(max_length=255, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='club',
            name='primary_position',
            field=models.CharField(help_text=b'Position of the primary contact', max_length=200, verbose_name=b'Position', blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='club',
            name='youtube',
            field=models.URLField(max_length=255, blank=True),
            preserve_default=True,
        ),
    ]