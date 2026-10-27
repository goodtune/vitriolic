# Stages or teams of a division that share an ``order`` are numbered 1, 2,
# 3, ... in the order they were listed, ahead of the constraint 0071 adds; a
# division whose rows are already distinct is left as it is, gaps and all.
#
# This is its own migration because PostgreSQL will not alter a table in the
# transaction that has updated its rows.

from django.db import migrations
from django.db.models import Count


def renumber(apps, model_name):
    model = apps.get_model("competition", model_name)
    shared = (
        model.objects.values("division_id", "order")
        .annotate(rows=Count("pk"))
        .filter(rows__gt=1)
        .values_list("division_id", flat=True)
    )
    for division_id in set(shared):
        rows = list(
            model.objects.filter(division_id=division_id).order_by("order", "pk")
        )
        # Two passes keep every value distinct along the way.
        offset = rows[-1].order
        for n, row in enumerate(rows, 1):
            model.objects.filter(pk=row.pk).update(order=offset + n)
        for n, row in enumerate(rows, 1):
            model.objects.filter(pk=row.pk).update(order=n)


def forwards(apps, schema_editor):
    renumber(apps, "Stage")
    renumber(apps, "Team")


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0069_list_ordering"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
