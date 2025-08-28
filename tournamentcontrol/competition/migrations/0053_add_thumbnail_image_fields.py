from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0052_add_club_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="season",
            name="live_stream_thumbnail_image",
            field=models.BinaryField(
                blank=True,
                null=True,
                editable=True,
                help_text="Binary data for thumbnail image to be used for YouTube videos",
            ),
        ),
        migrations.AddField(
            model_name="match",
            name="live_stream_thumbnail_image",
            field=models.BinaryField(
                blank=True,
                null=True,
                editable=True,
                help_text="Binary data for thumbnail image to be used for YouTube video",
            ),
        ),
    ]
