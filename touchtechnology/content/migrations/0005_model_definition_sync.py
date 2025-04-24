# -*- coding: utf-8 -*-

from django.db import migrations, models

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0004_remove_placeholderkeywordargument"),
    ]

    operations = [
        migrations.AlterField(
            model_name="page",
            name="last_modified",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="pagecontent",
            name="last_modified",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="redirect",
            name="active",
            field=touchtechnology.common.db.models.BooleanField(
                default=True, verbose_name="Active"
            ),
        ),
        migrations.AlterField(
            model_name="redirect",
            name="permanent",
            field=touchtechnology.common.db.models.BooleanField(
                default=False, verbose_name="Permanent"
            ),
        ),
    ]
