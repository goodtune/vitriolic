# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("competition", "0014_match_play_at_blank"),
    ]

    operations = [
        migrations.AddField(
            model_name="person",
            name="user",
            field=models.OneToOneField(
                null=True,
                blank=True,
                to=settings.AUTH_USER_MODEL,
                on_delete=models.deletion.PROTECT,
            ),
            preserve_default=True,
        ),
    ]
