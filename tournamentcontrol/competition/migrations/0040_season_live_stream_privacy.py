from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0039_season_live_stream"),
    ]

    operations = [
        migrations.AddField(
            model_name="season",
            name="live_stream_privacy",
            field=models.CharField(
                choices=[
                    ("public", "Public"),
                    ("private", "Private"),
                    ("unlisted", "Unlisted"),
                ],
                default="private",
                max_length=20,
            ),
        ),
    ]
