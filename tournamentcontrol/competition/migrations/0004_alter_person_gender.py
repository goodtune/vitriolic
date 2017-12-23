# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0003_division_draft_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='person',
            name='gender',
            field=models.CharField(max_length=1, choices=[(b'M', 'Male'), (b'F', 'Female'), (b'X', 'Unspecified')]),
            preserve_default=True,
        ),
    ]
