from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0048_season_live_stream_thumbnail"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="live_stream_thumbnail",
            field=models.URLField(blank=True, null=True),
        ),
    ]
