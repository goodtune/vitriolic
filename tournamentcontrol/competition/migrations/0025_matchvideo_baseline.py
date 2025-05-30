# -*- coding: utf-8 -*-

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0024_auto_20170203_0619"),
    ]

    operations = [
        migrations.AlterField(
            model_name="division",
            name="sportingpulse_url",
            field=models.URLField(
                blank=True, editable=False, max_length=1024, null=True
            ),
        ),
        migrations.AlterUniqueTogether(
            name="division",
            unique_together=set([("slug", "season"), ("title", "season")]),
        ),
        migrations.AlterUniqueTogether(
            name="season",
            unique_together=set([("slug", "competition"), ("title", "competition")]),
        ),
        migrations.AlterUniqueTogether(
            name="stage",
            unique_together=set([("slug", "division"), ("title", "division")]),
        ),
    ]
