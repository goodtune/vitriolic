# Add adhoc live stream events associated with a competition Season.
#
# Standalone feature: this migration only creates the new table, it does not
# alter any existing schema.

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
                    "stream_key",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "The stream key the camera or encoder operator should "
                            "use to deliver video for this event."
                        ),
                        max_length=50,
                        null=True,
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
