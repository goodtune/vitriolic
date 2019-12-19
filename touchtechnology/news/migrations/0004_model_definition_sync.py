# -*- coding: utf-8 -*-

from django.db import migrations, models

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0003_category_last_modified"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="category", options={"verbose_name_plural": "categories"},
        ),
        migrations.AlterField(
            model_name="article",
            name="is_active",
            field=touchtechnology.common.db.models.BooleanField(
                default=True, verbose_name="Enabled"
            ),
        ),
        migrations.AlterField(
            model_name="article",
            name="last_modified",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="article",
            name="published",
            field=models.DateTimeField(
                help_text="Set a date & time in the future to schedule an announcement.",
                verbose_name="Published",
            ),
        ),
        migrations.AlterField(
            model_name="article",
            name="slug_locked",
            field=touchtechnology.common.db.models.BooleanField(
                default=False, verbose_name="Locked Slug"
            ),
        ),
        migrations.AlterField(
            model_name="category",
            name="hidden_from_navigation",
            field=touchtechnology.common.db.models.BooleanField(
                default=False,
                help_text="When set to 'Yes' this object will still be available, but will not appear in menus.",
                verbose_name="Hide from menus",
            ),
        ),
        migrations.AlterField(
            model_name="category",
            name="is_active",
            field=touchtechnology.common.db.models.BooleanField(
                default=True, verbose_name="Enabled"
            ),
        ),
        migrations.AlterField(
            model_name="category",
            name="last_modified",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="category",
            name="slug_locked",
            field=touchtechnology.common.db.models.BooleanField(
                default=False, verbose_name="Locked Slug"
            ),
        ),
    ]
