# A provider may use one identifier in more than one season, so an
# ``upstream_id`` is unique only within the record's parent: a division's
# within its season, a team's within its division and a match's within its
# stage. The synchronisation looks a team or match up within the season it
# reconciles. Rows without an identifier never collide, since the database
# treats every NULL as distinct.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0076_scoreboard"),
    ]

    operations = [
        migrations.AlterField(
            model_name="division",
            name="upstream_id",
            field=models.CharField(
                blank=True, db_index=True, editable=False, max_length=255, null=True
            ),
        ),
        migrations.AlterField(
            model_name="team",
            name="upstream_id",
            field=models.CharField(
                blank=True, db_index=True, editable=False, max_length=255, null=True
            ),
        ),
        migrations.AlterField(
            model_name="match",
            name="upstream_id",
            field=models.CharField(
                blank=True, db_index=True, editable=False, max_length=255, null=True
            ),
        ),
        migrations.AddConstraint(
            model_name="division",
            constraint=models.UniqueConstraint(
                fields=["season", "upstream_id"],
                name="competition_division_unique_season_upstream_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="team",
            constraint=models.UniqueConstraint(
                fields=["division", "upstream_id"],
                name="competition_team_unique_division_upstream_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="match",
            constraint=models.UniqueConstraint(
                fields=["stage", "upstream_id"],
                name="competition_match_unique_stage_upstream_id",
            ),
        ),
    ]
