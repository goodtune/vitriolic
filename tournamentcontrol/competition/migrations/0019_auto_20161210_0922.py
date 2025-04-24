# -*- coding: utf-8 -*-

from django.db import migrations

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0018_resync_field_and_model_defs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="competition",
            name="clubs",
            field=touchtechnology.common.db.models.ManyToManyField(
                related_name="competitions", to="competition.Club", blank=True
            ),
        ),
    ]
