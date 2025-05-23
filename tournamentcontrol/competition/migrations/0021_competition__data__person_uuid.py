# -*- coding: utf-8 -*-

from django.db import migrations


def link_person_model(apps, schema_editor):
    Club = apps.get_model("competition", "Club")
    Person = apps.get_model("competition", "Person")

    # Update the Club.primary_uuid field, with no reverse relation we need to
    # edit it on the object directly.
    for club in Club.objects.exclude(primary__isnull=True):
        club.primary_uuid = club.primary
        club.save()

    # Update all the reverse relations per person.
    for person in Person.objects.all():
        person.clubassociation_set.update(person_uuid=person.uuid)
        person.teamassociation_set.update(person_uuid=person.uuid)
        person.seasonassociation_set.update(person_uuid=person.uuid)
        person.statistics.update(player_uuid=person.uuid)


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0020_competition__add__person_uuid"),
    ]

    operations = [
        migrations.RunPython(link_person_model, reverse_code=migrations.RunPython.noop),
    ]
