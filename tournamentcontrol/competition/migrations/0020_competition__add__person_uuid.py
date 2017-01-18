# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-01-17 20:19
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import touchtechnology.common.db.models
import uuid


def initial_uuid(apps, schema_editor):
    Person = apps.get_model('competition', 'Person')
    for p in Person.objects.select_for_update():
        p.uuid = uuid.uuid4()
        p.save()


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0019_auto_20161210_0922'),
    ]

    operations = [
		# Add the new uuid field to the Person model with null=True (will
		# breach NOT NULL constraints on creation if we don't do this)
        migrations.AddField(
            model_name='person',
            name='uuid',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                null=True,
            ),
        ),

        # Apply a data migration step to populate each existing instance with a
        # suitable uuid value
		migrations.RunPython(initial_uuid, reverse_code=migrations.RunPython.noop),

        # Now that all extsing records have a uuid value, alter the schema to
        # enforce the NOT NULL constraint moving forward
        migrations.AlterField(
            model_name='person',
            name='uuid',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
            ),
        ),

        # Each of the models which have a ForeignKey to the Person model we
        # need to add a new field which we can populate in a data migration;
        # each field needs to be NULL-able and must specify the "to_field"
        # attribute to make sure we point at the right field on the Person
        # model

        migrations.AddField(
            model_name='clubassociation',
            name='person_uuid',
            field=touchtechnology.common.db.models.ForeignKey(
                to='competition.Person',
                to_field=b'uuid',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='+',
                blank=True,
                null=True,
            ),
        ),

        migrations.AddField(
            model_name='seasonassociation',
            name='person_uuid',
            field=touchtechnology.common.db.models.ForeignKey(
                to='competition.Person',
                to_field=b'uuid',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='+',
                blank=True,
                null=True,
            ),
        ),

        migrations.AddField(
            model_name='teamassociation',
            name='person_uuid',
            field=touchtechnology.common.db.models.ForeignKey(
                to='competition.Person',
                to_field=b'uuid',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='+',
                blank=True,
                null=True,
            ),
        ),

        migrations.AddField(
            model_name='simplescorematchstatistic',
            name='player_uuid',
            field=touchtechnology.common.db.models.ForeignKey(
                to='competition.Person',
                to_field=b'uuid',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='+',
                blank=True,
                null=True,
            ),
        ),
    ]
