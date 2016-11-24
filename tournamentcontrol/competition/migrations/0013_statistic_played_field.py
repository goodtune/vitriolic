# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0012_hashtag_include_symbol'),
    ]

    operations = [
        migrations.AlterField(
            model_name='simplescorematchstatistic',
            name='played',
            field=models.SmallIntegerField(default=0, blank=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(1)]),
        ),
    ]
