# -*- coding: utf-8 -*-

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0027_matchvideo_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="matchvideo",
            name="match",
        ),
        migrations.DeleteModel(
            name="MatchVideo",
        ),
    ]
