# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0005_alter_club_facebook_youtube_position'),
    ]

    operations = [
        migrations.AddField(
            model_name='division',
            name='sportingpulse_url',
            field=models.URLField(help_text='Here be dragons! Enter at own risk!', max_length=1024, null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='match',
            name='external_identifier',
            field=models.CharField(db_index=True, max_length=20, unique=True, null=True, blank=True),
            preserve_default=True,
        ),
    ]
