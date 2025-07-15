import django.db.models.deletion
from django.db import migrations, models

import tournamentcontrol.highlights.constants as constants


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("competition", "0050_alter_place_timezone_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="BaseTemplate",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(unique=True)),
                (
                    "template_type",
                    models.CharField(
                        max_length=20, choices=constants.HighlightTemplateType.choices
                    ),
                ),
                ("svg", models.TextField()),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="SeasonTemplate",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(blank=True, max_length=100)),
                ("svg", models.TextField(blank=True)),
                ("config", models.JSONField(blank=True, default=dict)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                (
                    "base",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="season_templates",
                        to="highlights.basetemplate",
                    ),
                ),
                (
                    "season",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="highlight_templates",
                        to="competition.season",
                    ),
                ),
            ],
        ),
    ]
