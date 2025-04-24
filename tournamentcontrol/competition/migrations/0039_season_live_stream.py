from django.db import migrations

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0038_match_live_stream"),
    ]

    operations = [
        migrations.AddField(
            model_name="season",
            name="live_stream",
            field=touchtechnology.common.db.models.BooleanField(default=False),
        ),
    ]
