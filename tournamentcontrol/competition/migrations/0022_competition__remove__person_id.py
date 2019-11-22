# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import uuid

import django.db.models.deletion
import touchtechnology.common.db.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0021_competition__data__person_uuid"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="clubassociation", unique_together=set([("club", "person_uuid")]),
        ),
        migrations.AlterUniqueTogether(
            name="seasonassociation", unique_together=set([("season", "person_uuid")]),
        ),
        migrations.AlterUniqueTogether(
            name="teamassociation", unique_together=set([("team", "person_uuid")]),
        ),
        migrations.RemoveField(model_name="club", name="primary"),
        migrations.RemoveField(model_name="clubassociation", name="person"),
        migrations.RemoveField(model_name="seasonassociation", name="person"),
        migrations.RemoveField(model_name="teamassociation", name="person"),
        migrations.RemoveField(model_name="simplescorematchstatistic", name="player"),
        # Remove old related fields and rename new ones in place.
        migrations.RenameField("club", "primary_uuid", "primary"),
        migrations.RenameField("clubassociation", "person_uuid", "person"),
        migrations.RenameField("seasonassociation", "person_uuid", "person"),
        migrations.RenameField("teamassociation", "person_uuid", "person"),
        migrations.RenameField("simplescorematchstatistic", "player_uuid", "player"),
        # Modify the unique_together constraints again.
        migrations.AlterUniqueTogether(
            name="clubassociation", unique_together=set([("club", "person")]),
        ),
        migrations.AlterUniqueTogether(
            name="seasonassociation", unique_together=set([("season", "person")]),
        ),
        migrations.AlterUniqueTogether(
            name="teamassociation", unique_together=set([("team", "person")]),
        ),
        # Remove the old primary pk and promote the new one.
        migrations.RemoveField(model_name="person", name="id",),
        migrations.AlterField(
            model_name="person",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4, serialize=False, editable=False, unique=True,
            ),
        ),
        migrations.RunSQL(
            "SELECT 1;",
            "SELECT 1;",
            state_operations=[
                migrations.AlterField(
                    model_name="person",
                    name="uuid",
                    field=models.UUIDField(
                        primary_key=True,
                        default=uuid.uuid4,
                        serialize=False,
                        editable=False,
                    ),
                ),
            ],
        ),
        # Finally, resync with the models.py definitions
        migrations.AlterField(
            model_name="club",
            name="primary",
            field=touchtechnology.common.db.models.ForeignKey(
                to="competition.Person",
                related_name="+",
                blank=True,
                null=True,
                help_text="Appears on the front-end with other club information.",
                verbose_name="Primary contact",
                on_delete=django.db.models.deletion.PROTECT,
            ),
        ),
        migrations.AlterField(
            model_name="clubassociation",
            name="person",
            field=touchtechnology.common.db.models.ForeignKey(
                to="competition.Person", on_delete=django.db.models.deletion.PROTECT,
            ),
        ),
        migrations.AlterField(
            model_name="seasonassociation",
            name="person",
            field=touchtechnology.common.db.models.ForeignKey(
                to="competition.Person", on_delete=django.db.models.deletion.PROTECT
            ),
        ),
        migrations.AlterField(
            model_name="simplescorematchstatistic",
            name="player",
            field=touchtechnology.common.db.models.ForeignKey(
                related_name="statistics",
                to="competition.Person",
                on_delete=django.db.models.deletion.PROTECT,
            ),
        ),
        migrations.AlterField(
            model_name="teamassociation",
            name="person",
            field=touchtechnology.common.db.models.ForeignKey(
                to="competition.Person",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
            ),
        ),
    ]
