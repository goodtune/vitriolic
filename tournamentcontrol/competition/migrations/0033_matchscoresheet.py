# -*- coding: utf-8 -*-

import uuid

import cloudinary.models
import django.db.models.deletion
from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):

    dependencies = [("competition", "0032_resave_all_matches")]

    operations = [
        migrations.CreateModel(
            name="MatchScoreSheet",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "image",
                    cloudinary.models.CloudinaryField(
                        max_length=255, verbose_name=_("Image")
                    ),
                ),
                (
                    "match",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="competition.Match",
                        related_name="scoresheets",
                    ),
                ),
            ],
        )
    ]
