# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0008_nullable_statistics'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ByeTeam',
        ),
    ]
