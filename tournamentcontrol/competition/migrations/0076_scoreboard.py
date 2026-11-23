import django.core.validators
from django.db import migrations, models

import touchtechnology.common.db.models


class Migration(migrations.Migration):
    dependencies = [("competition", "0075_shirt_number_not_negative")]

    operations = [
        migrations.AlterModelOptions(
            name="season",
            options={
                "ordering": ("order",),
                "permissions": [
                    ("stream_season", "Can start and stop live streams for the season"),
                    (
                        "commentate_season",
                        "Can watch the commentary booths of the season",
                    ),
                    ("score_season", "Can keep the scoreboards of the season"),
                ],
            },
        ),
        migrations.AddField(
            model_name="venue",
            name="scoreboard_auto_start",
            field=touchtechnology.common.db.models.BooleanField(
                default=True,
                help_text=(
                    "The clock of each scoreboard at this venue starts at the "
                    "match's scheduled time. Turn it off to have the scorer start "
                    "each clock by hand."
                ),
                verbose_name="Start scoreboard clocks on time",
            ),
        ),
        migrations.AddField(
            model_name="division",
            name="periods",
            field=models.PositiveSmallIntegerField(
                blank=True,
                default=2,
                help_text="How many periods a match is played in: 2 for halves.",
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="Periods",
            ),
        ),
        migrations.AddField(
            model_name="division",
            name="period_minutes",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text=(
                    "Minutes in each period. Leave it empty for a scoreboard with "
                    "no clock."
                ),
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="Period length",
            ),
        ),
        migrations.AddField(
            model_name="division",
            name="break_minutes",
            field=models.PositiveSmallIntegerField(
                blank=True,
                default=0,
                help_text="Minutes between one period and the next.",
                verbose_name="Break length",
            ),
        ),
        migrations.AddField(
            model_name="match",
            name="home_team_progress_score",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="match",
            name="away_team_progress_score",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="match",
            name="clock_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stage",
            name="periods",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text=("Leave it empty to use the division's number of periods."),
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="Periods",
            ),
        ),
        migrations.AddField(
            model_name="stage",
            name="period_minutes",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text=(
                    "Minutes in each period. Leave it empty to use the division's."
                ),
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="Period length",
            ),
        ),
        migrations.AddField(
            model_name="stage",
            name="break_minutes",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text=(
                    "Minutes between one period and the next. Leave it empty to use the division's."
                ),
                null=True,
                verbose_name="Break length",
            ),
        ),
        migrations.AddField(
            model_name="match",
            name="periods",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text=("Leave it empty to use the stage's number of periods."),
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="Periods",
            ),
        ),
        migrations.AddField(
            model_name="match",
            name="period_minutes",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text=(
                    "Minutes in each period. Leave it empty to use the stage's."
                ),
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="Period length",
            ),
        ),
        migrations.AddField(
            model_name="match",
            name="break_minutes",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text=(
                    "Minutes between one period and the next. Leave it empty to use the stage's."
                ),
                null=True,
                verbose_name="Break length",
            ),
        ),
    ]
