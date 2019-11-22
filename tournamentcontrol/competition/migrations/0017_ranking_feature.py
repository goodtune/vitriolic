# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.db.models.deletion
import tournamentcontrol.competition.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0016_season_forfeit_notifications"),
    ]

    operations = [
        migrations.AddField(
            model_name="competition",
            name="rank_importance",
            field=models.DecimalField(
                max_digits=6, decimal_places=3, blank=True, null=True
            ),
        ),
        migrations.AddField(
            model_name="season",
            name="rank_importance",
            field=models.DecimalField(
                max_digits=6, decimal_places=3, blank=True, null=True
            ),
        ),
        migrations.AddField(
            model_name="division",
            name="rank_importance",
            field=models.DecimalField(
                max_digits=6, decimal_places=3, blank=True, null=True
            ),
        ),
        migrations.AddField(
            model_name="stage",
            name="rank_importance",
            field=models.DecimalField(
                max_digits=6, decimal_places=3, blank=True, null=True
            ),
        ),
        migrations.AddField(
            model_name="stagegroup",
            name="rank_importance",
            field=models.DecimalField(
                max_digits=6, decimal_places=3, blank=True, null=True
            ),
        ),
        migrations.AddField(
            model_name="match",
            name="rank_importance",
            field=models.DecimalField(
                max_digits=6, decimal_places=3, blank=True, null=True
            ),
        ),
        migrations.CreateModel(
            name="RankDivision",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("title", models.CharField(verbose_name="Title", max_length=255)),
                (
                    "short_title",
                    models.CharField(
                        verbose_name="Short title",
                        blank=True,
                        help_text="This is used in navigation menus instead of the longer title value.",
                        max_length=100,
                    ),
                ),
                ("slug", models.SlugField(verbose_name="Slug", max_length=255)),
                (
                    "slug_locked",
                    models.BooleanField(verbose_name="Slug locked", default=False),
                ),
                ("order", models.PositiveIntegerField(default=1)),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={"ordering": ("order",), "abstract": False,},
            bases=(tournamentcontrol.competition.models.AdminUrlMixin, models.Model),
        ),
        migrations.CreateModel(
            name="RankPoints",
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
                (
                    "points",
                    models.DecimalField(default=0, max_digits=6, decimal_places=3),
                ),
                ("date", models.DateField()),
            ],
            options={"ordering": ("-date", "team", "-points"),},
        ),
        migrations.CreateModel(
            name="RankTeam",
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
            ],
            options={"ordering": ("division",),},
        ),
        migrations.AddField(
            model_name="division",
            name="rank_division",
            field=models.ForeignKey(
                null=True,
                blank=True,
                to="competition.RankDivision",
                on_delete=django.db.models.deletion.PROTECT,
            ),
        ),
        migrations.AddField(
            model_name="team",
            name="rank_division",
            field=models.ForeignKey(
                null=True,
                blank=True,
                to="competition.RankDivision",
                on_delete=django.db.models.deletion.PROTECT,
            ),
        ),
        migrations.AddField(
            model_name="rankteam",
            name="club",
            field=models.ForeignKey(
                to="competition.Club", on_delete=django.db.models.deletion.PROTECT
            ),
        ),
        migrations.AddField(
            model_name="rankteam",
            name="division",
            field=models.ForeignKey(
                to="competition.RankDivision",
                on_delete=django.db.models.deletion.PROTECT,
            ),
        ),
        migrations.AlterUniqueTogether(
            name="rankteam", unique_together=set([("club", "division")]),
        ),
        migrations.AddField(
            model_name="rankpoints",
            name="team",
            field=models.ForeignKey(
                to="competition.RankTeam", on_delete=django.db.models.deletion.PROTECT
            ),
        ),
    ]
