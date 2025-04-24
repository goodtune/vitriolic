# -*- coding: utf-8 -*-

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0023_competition__add__match_uuid_finalize"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="competition",
            options={"ordering": ("order",)},
        ),
        migrations.AlterModelOptions(
            name="division",
            options={"ordering": ("order",)},
        ),
        migrations.AlterModelOptions(
            name="season",
            options={"ordering": ("order",)},
        ),
    ]
