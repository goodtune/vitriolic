from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("competition", "0064_mysideline_titles")]

    operations = [
        migrations.AddField(
            model_name="match",
            name="live_stream_status",
            field=models.CharField(blank=True, db_index=True, max_length=10, null=True),
        ),
        migrations.AddField(
            model_name="match",
            name="live_stream_status_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="livestreamevent",
            name="live_stream_status",
            field=models.CharField(blank=True, db_index=True, max_length=10, null=True),
        ),
        migrations.AddField(
            model_name="livestreamevent",
            name="live_stream_status_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name="season",
            options={
                "ordering": ("order",),
                "permissions": [
                    ("stream_season", "Can start and stop live streams for the season")
                ],
            },
        ),
    ]
