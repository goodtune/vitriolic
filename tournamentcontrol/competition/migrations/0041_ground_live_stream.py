from django.db import migrations

import touchtechnology.common.db.models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0040_season_live_stream_privacy"),
    ]

    operations = [
        migrations.AddField(
            model_name="ground",
            name="live_stream",
            field=touchtechnology.common.db.models.BooleanField(default=False),
        ),
    ]
