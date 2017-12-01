# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='division',
            name='draft',
            field=models.BooleanField(default=True, help_text='Marking a division as draft will prevent matches from being visible in the front-end.'),
            preserve_default=True,
        ),
    ]
