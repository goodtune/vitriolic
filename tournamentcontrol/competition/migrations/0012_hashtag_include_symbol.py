# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.core.validators
from django.db import migrations, models


def prefix_with_hash(apps, schema_editor):
    Season = apps.get_model("competition", "Season")
    for season in Season.objects.exclude(hashtag__isnull=True):
        season.hashtag = f"#{season.hashtag}"
        season.save()


def remove_hash_prefix(apps, schema_editor):
    Season = apps.get_model("competition", "Season")
    for season in Season.objects.filter(hashtag__startswith="#"):
        season.hashtag = season.hashtag[1:]
        season.save()


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0011_custom_twitter_ladderpoints_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="season",
            name="hashtag",
            field=models.CharField(
                validators=[
                    django.core.validators.RegexValidator(
                        b"^(?:#)(\\w+)$",
                        "Enter a valid value. Make sure you include the # symbol.",
                    )
                ],
                max_length=30,
                blank=True,
                help_text="Your official <em>hash tag</em> for social media promotions.",
                null=True,
                verbose_name="Hash Tag",
            ),
        ),
        migrations.RunPython(prefix_with_hash, remove_hash_prefix),
    ]
