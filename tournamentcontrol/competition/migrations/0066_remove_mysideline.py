# Drop the MySideline-specific columns that 0065_upstream replaced with
# provider-neutral ones, and rename the remaining MySideline columns to match.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0065_upstream"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="season",
            name="mysideline_season",
        ),
        migrations.RemoveField(
            model_name="season",
            name="mysideline_season_tag",
        ),
        migrations.RemoveField(
            model_name="division",
            name="mysideline_id",
        ),
        migrations.RemoveField(
            model_name="team",
            name="mysideline_id",
        ),
        migrations.RemoveField(
            model_name="match",
            name="mysideline_id",
        ),
        migrations.RenameField(
            model_name="competition",
            old_name="mysideline_url",
            new_name="upstream_url",
        ),
        migrations.AlterField(
            model_name="competition",
            name="upstream_url",
            field=models.URLField(
                blank=True,
                help_text=(
                    "The organisation's page on the competition management provider "
                    "that publishes its draws, for example "
                    "https://tfa.mysideline.com.au/competitions/association/6338 "
                    "(MySideline) or https://www.revolutionise.com.au/ccha/games "
                    "(revolutioniseSPORT). Seasons that name an upstream URL are then "
                    "synchronised from the provider, which is authoritative for their "
                    "divisions, teams, fixtures and results."
                ),
                max_length=1024,
                null=True,
                verbose_name="Upstream URL",
            ),
        ),
        migrations.RenameField(
            model_name="division",
            old_name="mysideline_title",
            new_name="upstream_title",
        ),
        migrations.RenameField(
            model_name="division",
            old_name="mysideline_title_synced",
            new_name="upstream_title_synced",
        ),
        migrations.RenameField(
            model_name="team",
            old_name="mysideline_title",
            new_name="upstream_title",
        ),
        migrations.RenameField(
            model_name="team",
            old_name="mysideline_title_synced",
            new_name="upstream_title_synced",
        ),
    ]
