# -*- coding: utf-8 -*-

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0003_drop_pythonpackage"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitemapnode",
            name="kwargs",
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
    ]
