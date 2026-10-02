from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0058_populate_color_fields"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="clubassociation",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="division",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="divisionexclusiondate",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="laddersummary",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="season",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="seasonassociation",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="seasonexclusiondate",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="seasonreferee",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="stage",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="stagegroup",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="team",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="teamassociation",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="clubassociation",
            constraint=models.UniqueConstraint(
                fields=["club", "person"],
                name="competition_clubassociation_unique_club_person",
            ),
        ),
        migrations.AddConstraint(
            model_name="division",
            constraint=models.UniqueConstraint(
                fields=["title", "season"],
                name="competition_division_unique_title_season",
            ),
        ),
        migrations.AddConstraint(
            model_name="division",
            constraint=models.UniqueConstraint(
                fields=["slug", "season"],
                name="competition_division_unique_slug_season",
            ),
        ),
        migrations.AddConstraint(
            model_name="divisionexclusiondate",
            constraint=models.UniqueConstraint(
                fields=["division", "date"],
                name="competition_divisionexclusiondate_unique_division_date",
            ),
        ),
        migrations.AddConstraint(
            model_name="laddersummary",
            constraint=models.UniqueConstraint(
                fields=["stage", "team"],
                name="competition_laddersummary_unique_stage_team",
            ),
        ),
        migrations.AddConstraint(
            model_name="season",
            constraint=models.UniqueConstraint(
                fields=["title", "competition"],
                name="competition_season_unique_title_competition",
            ),
        ),
        migrations.AddConstraint(
            model_name="season",
            constraint=models.UniqueConstraint(
                fields=["slug", "competition"],
                name="competition_season_unique_slug_competition",
            ),
        ),
        migrations.AddConstraint(
            model_name="seasonassociation",
            constraint=models.UniqueConstraint(
                fields=["season", "person"],
                name="competition_seasonassociation_unique_season_person",
            ),
        ),
        migrations.AddConstraint(
            model_name="seasonexclusiondate",
            constraint=models.UniqueConstraint(
                fields=["season", "date"],
                name="competition_seasonexclusiondate_unique_season_date",
            ),
        ),
        migrations.AddConstraint(
            model_name="seasonreferee",
            constraint=models.UniqueConstraint(
                fields=["season", "person"],
                name="competition_seasonreferee_unique_season_person",
            ),
        ),
        migrations.AddConstraint(
            model_name="stage",
            constraint=models.UniqueConstraint(
                fields=["title", "division"],
                name="competition_stage_unique_title_division",
            ),
        ),
        migrations.AddConstraint(
            model_name="stage",
            constraint=models.UniqueConstraint(
                fields=["slug", "division"],
                name="competition_stage_unique_slug_division",
            ),
        ),
        migrations.AddConstraint(
            model_name="stagegroup",
            constraint=models.UniqueConstraint(
                fields=["stage", "order"],
                name="competition_stagegroup_unique_stage_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="team",
            constraint=models.UniqueConstraint(
                fields=["title", "division"],
                name="competition_team_unique_title_division",
            ),
        ),
        migrations.AddConstraint(
            model_name="teamassociation",
            constraint=models.UniqueConstraint(
                fields=["team", "person"],
                name="competition_teamassociation_unique_team_person",
            ),
        ),
    ]
