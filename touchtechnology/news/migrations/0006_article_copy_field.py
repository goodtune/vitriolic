from django.db import migrations

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0005_auto_20191122_1340"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="copy",
            field=touchtechnology.common.db.models.HTMLField(
                blank=True, verbose_name="Copy"
            ),
        ),
    ]
