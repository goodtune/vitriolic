from django.db import migrations

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0037_alter_match_evaluated"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="live_stream",
            field=touchtechnology.common.db.models.BooleanField(default=False),
        ),
    ]
