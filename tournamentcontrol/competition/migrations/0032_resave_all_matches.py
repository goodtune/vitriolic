# -*- coding: utf-8 -*-

from django.db import migrations

from tournamentcontrol.competition.signals.matches import match_saved_handler


def resave_all_matches(apps, schema_editor):
    Match = apps.get_model("competition", "Match")
    for m in Match.objects.all():
        # We have to manually exercise the match_saved_handler code because migrations use a proxy
        # model (ie. the "frozen" representation) and our handlers are attached on the fair-dinkum
        # model.  This will work because we don't use the `sender` in our handler - otherwise we'd
        # need to refactor the handler.
        match_saved_handler(None, m, False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [("competition", "0031_model_definition_sync")]

    operations = [migrations.RunPython(resave_all_matches, noop)]
