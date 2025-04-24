from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0047_season_live_stream_oauth2"),
    ]

    operations = [
        migrations.AddField(
            model_name="season",
            name="live_stream_thumbnail",
            field=models.URLField(null=True),
        ),
    ]
