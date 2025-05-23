import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0035_season_disable_calendar"),
    ]

    operations = [
        migrations.AlterField(
            model_name="divisionexclusiondate",
            name="division",
            field=touchtechnology.common.db.models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="exclusions",
                to="competition.Division",
            ),
        ),
        migrations.AlterField(
            model_name="ground",
            name="place_ptr",
            field=models.OneToOneField(
                auto_created=True,
                on_delete=django.db.models.deletion.CASCADE,
                parent_link=True,
                primary_key=True,
                serialize=False,
                to="competition.Place",
            ),
        ),
        migrations.AlterField(
            model_name="ladderentry",
            name="match",
            field=touchtechnology.common.db.models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ladder_entries",
                to="competition.Match",
            ),
        ),
        migrations.AlterField(
            model_name="ladderentry",
            name="team",
            field=touchtechnology.common.db.models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ladder_entries",
                to="competition.Team",
            ),
        ),
        migrations.AlterField(
            model_name="laddersummary",
            name="stage",
            field=touchtechnology.common.db.models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ladder_summary",
                to="competition.Stage",
            ),
        ),
        migrations.AlterField(
            model_name="laddersummary",
            name="stage_group",
            field=touchtechnology.common.db.models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ladder_summary",
                to="competition.StageGroup",
            ),
        ),
        migrations.AlterField(
            model_name="person",
            name="gender",
            field=models.CharField(
                choices=[("M", "Male"), ("F", "Female"), ("X", "Unspecified")],
                max_length=1,
            ),
        ),
        migrations.AlterField(
            model_name="rankpoints",
            name="team",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="competition.RankTeam"
            ),
        ),
        migrations.AlterField(
            model_name="rankteam",
            name="club",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="competition.Club"
            ),
        ),
        migrations.AlterField(
            model_name="rankteam",
            name="division",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="competition.RankDivision",
            ),
        ),
        migrations.AlterField(
            model_name="season",
            name="hashtag",
            field=models.CharField(
                blank=True,
                help_text="Your official <em>hash tag</em> for social media promotions.",
                max_length=30,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        "^(?:#)(\\w+)$",
                        "Enter a valid value. Make sure you include the # symbol.",
                    )
                ],
                verbose_name="Hash Tag",
            ),
        ),
        migrations.AlterField(
            model_name="seasonexclusiondate",
            name="season",
            field=touchtechnology.common.db.models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="exclusions",
                to="competition.Season",
            ),
        ),
        migrations.AlterField(
            model_name="seasonmatchtime",
            name="season",
            field=touchtechnology.common.db.models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="timeslots",
                to="competition.Season",
            ),
        ),
        migrations.AlterField(
            model_name="venue",
            name="place_ptr",
            field=models.OneToOneField(
                auto_created=True,
                on_delete=django.db.models.deletion.CASCADE,
                parent_link=True,
                primary_key=True,
                serialize=False,
                to="competition.Place",
            ),
        ),
    ]
