# -*- coding: utf-8 -*-

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0008_nullable_statistics"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ByeTeam",
        ),
    ]
