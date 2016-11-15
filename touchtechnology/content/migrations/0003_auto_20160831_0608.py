# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0002_last_modified'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='placeholder',
            options={'ordering': ('path',)},
        ),
        migrations.AlterField(
            model_name='pagecontent',
            name='label',
            field=models.SlugField(choices=[('copy', 'copy')], default='copy', max_length=20, verbose_name='CSS class'),
        ),
    ]
