# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.db.models.deletion
import touchtechnology.common.db.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0017_ranking_feature"),
    ]
    operations = [
        migrations.AlterModelOptions(
            name="clubassociation",
            options={
                "ordering": ("person__last_name", "person__first_name"),
                "verbose_name": "Official",
                "verbose_name_plural": "Officials",
            },
        ),
        migrations.AlterModelOptions(name="competition", options={},),
        migrations.AlterModelOptions(name="division", options={},),
        migrations.AlterModelOptions(
            name="divisionexclusiondate", options={"verbose_name": "exclusion date"},
        ),
        migrations.AlterModelOptions(
            name="drawformat", options={"ordering": ("teams", "name")},
        ),
        migrations.AlterModelOptions(
            name="match",
            options={
                "get_latest_by": "datetime",
                "ordering": (
                    "date",
                    "stage",
                    "round",
                    "is_bye",
                    "time",
                    "play_at__ground__order",
                    "pk",
                ),
                "verbose_name_plural": "matches",
            },
        ),
        migrations.AlterModelOptions(
            name="person",
            options={
                "ordering": ("last_name", "first_name"),
                "verbose_name_plural": "people",
            },
        ),
        migrations.AlterModelOptions(name="season", options={},),
        migrations.AlterModelOptions(
            name="seasonexclusiondate",
            options={"ordering": ("date",), "verbose_name": "exclusion date",},
        ),
        migrations.AlterModelOptions(
            name="seasonmatchtime", options={"verbose_name": "time slot",},
        ),
        migrations.AlterModelOptions(
            name="simplescorematchstatistic",
            options={"get_latest_by": "match", "ordering": ("match", "number"),},
        ),
        migrations.AlterModelOptions(
            name="stagegroup",
            options={"ordering": ("order",), "verbose_name": "pool",},
        ),
        migrations.AlterModelOptions(
            name="team",
            options={
                "ordering": (
                    "-division__season__start_date",
                    "division__order",
                    "stage_group__order",
                    "order",
                ),
            },
        ),
        migrations.AlterModelOptions(
            name="teamassociation",
            options={
                "ordering": (
                    "-is_player",
                    "number",
                    "person__last_name",
                    "person__first_name",
                ),
                "verbose_name": "linked person",
                "verbose_name_plural": "linked people",
            },
        ),
        migrations.AlterModelOptions(
            name="undecidedteam", options={"ordering": ("stage_group", "formula")},
        ),
        migrations.AlterField(
            model_name="club",
            name="primary",
            field=touchtechnology.common.db.models.ForeignKey(
                to="competition.Person",
                verbose_name="Primary contact",
                related_name="+",
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                help_text="Appears on the front-end with other club " "information.",
            ),
        ),
        migrations.AlterField(
            model_name="division",
            name="draft",
            field=models.BooleanField(
                default=False,
                help_text="Marking a division as draft will prevent matches "
                "from being visible in the front-end.",
            ),
        ),
        migrations.AlterField(
            model_name="division",
            name="games_per_day",
            field=models.SmallIntegerField(
                null=True,
                help_text="In Tournament mode, specify how many matches per "
                "day should be scheduled by the automatic draw "
                "generator.",
            ),
        ),
        migrations.AlterField(
            model_name="division",
            name="include_forfeits_in_played",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="match",
            name="away_team_eval_related",
            field=touchtechnology.common.db.models.ForeignKey(
                to="competition.Match",
                related_name="+",
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
            ),
        ),
        migrations.AlterField(
            model_name="match",
            name="forfeit_winner",
            field=touchtechnology.common.db.models.ForeignKey(
                to="competition.Team",
                related_name="+",
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
            ),
        ),
        migrations.AlterField(
            model_name="match",
            name="home_team_eval_related",
            field=touchtechnology.common.db.models.ForeignKey(
                to="competition.Match",
                related_name="+",
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
            ),
        ),
        migrations.AlterField(
            model_name="person",
            name="email",
            field=models.EmailField(max_length=254, blank=True),
        ),
        migrations.AlterField(
            model_name="person",
            name="first_name",
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name="person",
            name="last_name",
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name="season",
            name="mvp_results_public",
            field=touchtechnology.common.db.models.DateTimeField(
                verbose_name="MVP public at",
                null=True,
                blank=True,
                help_text="The time when the results of the MVP voting will "
                "be made public on the website. Leave blank to show "
                "at all times.",
            ),
        ),
        migrations.AlterField(
            model_name="simplescorematchstatistic",
            name="mvp",
            field=models.SmallIntegerField(verbose_name="MVP", null=True, blank=True,),
        ),
        migrations.AlterField(
            model_name="simplescorematchstatistic",
            name="points",
            field=models.SmallIntegerField(
                verbose_name="Points", null=True, blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="stage",
            name="carry_ladder",
            field=models.BooleanField(
                verbose_name="Carry over points",
                default=False,
                help_text="Set this to <b>Yes</b> if this stage should carry "
                "over values from the previous stage.",
            ),
        ),
        migrations.AlterField(
            model_name="stage",
            name="follows",
            field=touchtechnology.common.db.models.ForeignKey(
                to="competition.Stage",
                related_name="preceeds",
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                help_text="When progressing teams into this stage, which "
                "earlier stage should be used for determining "
                "positions.<br />Default is the immediately "
                "preceeding stage.",
            ),
        ),
        migrations.AlterField(
            model_name="stage",
            name="keep_ladder",
            field=models.BooleanField(
                verbose_name="Keep a ladder",
                default=True,
                help_text="Set this to <b>No</b> if this stage does not need "
                "to keep a competition ladder.<br />Usually set to "
                "No for a Final Series or a Knockout stage.",
            ),
        ),
        migrations.AlterField(
            model_name="stage",
            name="keep_mvp",
            field=models.BooleanField(
                verbose_name="Keep MVP stats",
                default=True,
                help_text="Set this to <b>No</b> if this stage does not need "
                "to keep track of MVP points.<br />Usually set to "
                "No for a Final Series.",
            ),
        ),
        migrations.AlterField(
            model_name="stage",
            name="scale_group_points",
            field=models.BooleanField(
                default=False,
                help_text="In stages with multiple pools, adjust points in "
                "the smaller groups to compensate for the reduced "
                "opportunity to score points.<br />"
                "You <strong>should</strong> also set 0 points for "
                "Bye matches.",
            ),
        ),
        migrations.AlterField(
            model_name="stagegroup",
            name="carry_ladder",
            field=models.BooleanField(
                verbose_name="Carry over points",
                default=False,
                help_text="Set this to <b>Yes</b> if the ladder for this pool "
                "should carry over values from the previous "
                "stage.<br />"
                "Will only apply for matches played against teams "
                "that are now in this group.",
            ),
        ),
        migrations.AlterField(
            model_name="team",
            name="names_locked",
            field=models.BooleanField(
                default=False,
                help_text="When the team name is locked, the team manager "
                "will not be able to change their team name.<br />"
                "As a tournament manager you can always change the "
                "names.",
            ),
        ),
    ]
