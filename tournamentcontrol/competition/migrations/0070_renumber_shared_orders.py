# Stages of a division that share an ``order`` are numbered 1, 2, 3, ... in
# the order they were listed, ahead of the constraint 0071 adds; a division
# whose stages are already distinct is left as it is, gaps and all.
#
# This is its own migration because PostgreSQL will not alter a table in the
# transaction that has updated its rows.

from django.db import migrations
from django.db.models import Count


def forwards(apps, schema_editor):
    Stage = apps.get_model("competition", "Stage")
    shared = (
        Stage.objects.values("division_id", "order")
        .annotate(rows=Count("pk"))
        .filter(rows__gt=1)
        .values_list("division_id", flat=True)
    )
    for division_id in set(shared):
        stages = list(
            Stage.objects.filter(division_id=division_id).order_by("order", "pk")
        )
        # Two passes keep every value distinct along the way.
        offset = stages[-1].order
        for n, stage in enumerate(stages, 1):
            Stage.objects.filter(pk=stage.pk).update(order=offset + n)
        for n, stage in enumerate(stages, 1):
            Stage.objects.filter(pk=stage.pk).update(order=n)


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0069_list_ordering"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
