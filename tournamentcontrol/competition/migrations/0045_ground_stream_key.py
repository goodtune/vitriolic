from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0044_match_live_stream_bind"),
    ]

    operations = [
        migrations.AddField(
            model_name="ground",
            name="stream_key",
            field=models.CharField(
                blank=True, db_index=True, max_length=50, null=True, unique=True
            ),
        ),
    ]
