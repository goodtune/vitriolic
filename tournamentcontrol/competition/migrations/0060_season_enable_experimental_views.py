# Add per-season opt-in flag for experimental spectator views.

from django.db import migrations

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0059_migrate_unique_together_to_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="season",
            name="enable_experimental_views",
            field=touchtechnology.common.db.models.BooleanField(
                default=False,
                help_text=(
                    "Set to expose experimental spectator views "
                    "(fixtures navigator, team timeline) for this "
                    "season. When unset those views return Not Found, "
                    "so existing seasons are unaffected."
                ),
                verbose_name="Enable experimental views",
            ),
        ),
    ]
