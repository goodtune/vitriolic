# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('competition', '0015_person_user_relation'),
    ]

    operations = [
        migrations.AddField(
            model_name='season',
            name='forfeit_notifications',
            field=models.ManyToManyField(help_text='When a team advises they are forfeiting, notify the opposition team plus these people.', to=settings.AUTH_USER_MODEL, blank=True),
        ),
    ]
