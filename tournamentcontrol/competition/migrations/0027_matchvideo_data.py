# -*- coding: utf-8 -*-

from django.db import migrations


def populate_videos(apps, schema_editor):
    Match = apps.get_model("competition", "Match")
    for match in Match.objects.all():
        match.videos = [video.url for video in match.matchvideo_set.all()]
        match.save()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0026_matchvideo"),
    ]

    operations = [
        migrations.RunPython(populate_videos, noop),
    ]
