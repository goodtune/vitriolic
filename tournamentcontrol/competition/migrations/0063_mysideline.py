# Replace the long-dead SportingPulse hook on Division with MySideline
# synchronisation configuration on Season and stable MySideline identifiers
# on the entities the synchronisation manages.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0062_fix_cross_stage_ladder_summary_pool"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="division",
            name="sportingpulse_url",
        ),
        migrations.AddField(
            model_name="season",
            name="mysideline_url",
            field=models.URLField(
                blank=True,
                help_text=(
                    "Association URL on MySideline, for example "
                    "https://tfa.mysideline.com.au/competitions/association/6338. "
                    "When set, divisions, teams, fixtures and results are "
                    "synchronised from MySideline and MySideline is authoritative."
                ),
                max_length=1024,
                null=True,
                verbose_name="MySideline URL",
            ),
        ),
        migrations.AddField(
            model_name="season",
            name="mysideline_season",
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    "Only synchronise MySideline competitions from this season "
                    "(a year, for example 2026). Leave blank for all seasons "
                    "listed for the association."
                ),
                null=True,
                verbose_name="MySideline season",
            ),
        ),
        migrations.AddField(
            model_name="season",
            name="mysideline_season_tag",
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[(1, "First half (winter)"), (2, "Second half (summer)")],
                help_text=(
                    "Only synchronise MySideline competitions from this period of "
                    "the season. Leave blank for the whole season."
                ),
                null=True,
                verbose_name="MySideline season period",
            ),
        ),
        migrations.AddField(
            model_name="division",
            name="mysideline_id",
            field=models.BigIntegerField(
                blank=True, editable=False, null=True, unique=True
            ),
        ),
        migrations.AddField(
            model_name="team",
            name="mysideline_id",
            field=models.BigIntegerField(
                blank=True, editable=False, null=True, unique=True
            ),
        ),
        migrations.AddField(
            model_name="match",
            name="mysideline_id",
            field=models.BigIntegerField(
                blank=True, editable=False, null=True, unique=True
            ),
        ),
    ]
