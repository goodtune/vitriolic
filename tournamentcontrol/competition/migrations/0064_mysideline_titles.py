# Track the MySideline name of a division or team alongside our own, so that
# a local name can be kept in place of unwieldy upstream naming and an
# upstream rename can still be reported rather than silently discarded.

from django.db import migrations, models


def adopt_remote_titles(apps, schema_editor):
    """
    Everything linked before this migration took its name from MySideline
    verbatim, so the current title is both the remote name and the value it
    was last reconciled with; neither is reported as a variation.
    """
    for model_name in ("Division", "Team"):
        model = apps.get_model("competition", model_name)
        model.objects.filter(mysideline_id__isnull=False).update(
            mysideline_title=models.F("title"),
            mysideline_title_synced=models.F("title"),
        )


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0063_mysideline"),
    ]

    operations = [
        migrations.AddField(
            model_name="division",
            name="mysideline_title",
            field=models.CharField(
                blank=True, editable=False, max_length=255, null=True
            ),
        ),
        migrations.AddField(
            model_name="division",
            name="mysideline_title_synced",
            field=models.CharField(
                blank=True, editable=False, max_length=255, null=True
            ),
        ),
        migrations.AddField(
            model_name="team",
            name="mysideline_title",
            field=models.CharField(
                blank=True, editable=False, max_length=255, null=True
            ),
        ),
        migrations.AddField(
            model_name="team",
            name="mysideline_title_synced",
            field=models.CharField(
                blank=True, editable=False, max_length=255, null=True
            ),
        ),
        migrations.RunPython(adopt_remote_titles, migrations.RunPython.noop),
    ]
