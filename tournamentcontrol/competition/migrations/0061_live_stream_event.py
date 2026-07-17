# Add adhoc live stream events associated with a competition Season.

import django.db.models.deletion
from django.db import migrations, models

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0060_season_enable_experimental_views"),
    ]

    operations = [
        migrations.CreateModel(
            name="LiveStreamEvent",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        help_text="Title of the broadcast on the YouTube platform.",
                        max_length=100,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Description of the broadcast on the YouTube platform.",
                    ),
                ),
                (
                    "start",
                    touchtechnology.common.db.models.DateTimeField(
                        help_text="When the live stream is scheduled to commence.",
                        verbose_name="Scheduled start",
                    ),
                ),
                (
                    "stop",
                    touchtechnology.common.db.models.DateTimeField(
                        help_text="When the live stream is scheduled to conclude.",
                        verbose_name="Scheduled finish",
                    ),
                ),
                (
                    "live_stream",
                    touchtechnology.common.db.models.BooleanField(
                        default=True,
                        help_text=(
                            "Set to No to remove the scheduled broadcast from the "
                            "YouTube platform while keeping this event for your "
                            "records."
                        ),
                    ),
                ),
                (
                    "external_identifier",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=20,
                        null=True,
                        unique=True,
                    ),
                ),
                (
                    "live_stream_bind",
                    models.CharField(
                        blank=True, db_index=True, max_length=50, null=True
                    ),
                ),
                (
                    "live_stream_thumbnail_image",
                    models.BinaryField(
                        blank=True,
                        editable=True,
                        help_text=(
                            "Image to be used as thumbnail image on the YouTube "
                            "platform"
                        ),
                        null=True,
                    ),
                ),
                (
                    "ground",
                    touchtechnology.common.db.models.ForeignKey(
                        blank=True,
                        help_text=(
                            "The stream (camera) that will broadcast this event — "
                            "the broadcast will be bound to this ground's stream "
                            "key."
                        ),
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="live_stream_events",
                        to="competition.ground",
                    ),
                ),
                (
                    "season",
                    touchtechnology.common.db.models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="live_stream_events",
                        to="competition.season",
                    ),
                ),
            ],
            options={
                "ordering": ("start", "title"),
                "verbose_name": "live stream event",
            },
        ),
    ]
