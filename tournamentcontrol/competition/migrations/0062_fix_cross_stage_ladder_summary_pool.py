# Data migration to detach ladder summaries from pools in a different stage.

from django.db import migrations
from django.db.models import F


def clear_cross_stage_stage_group(apps, schema_editor):
    """
    A ``LadderSummary`` used to inherit the ``stage_group`` of the team rather
    than of the stage the summary belongs to. Where a team played in a later
    stage which does not have pools, the summary for that stage was attributed
    to the pool the team was drawn into for an earlier stage, and was therefore
    reported as part of that pool's ladder as well as its own stage.
    """
    LadderSummary = apps.get_model("competition", "LadderSummary")
    LadderSummary.objects.filter(stage_group__isnull=False).exclude(
        stage_group__stage=F("stage")
    ).update(stage_group=None)


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0061_live_stream_event"),
    ]

    operations = [
        migrations.RunPython(
            clear_cross_stage_stage_group,
            reverse_code=migrations.RunPython.noop,
            elidable=True,
        ),
    ]
