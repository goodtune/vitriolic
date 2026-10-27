# The teams and stages of each division are numbered 1, 2, 3, ... in the
# order they were listed, ahead of the constraint 0073 adds to teams: rows
# that shared a value are told apart by their keys, and gaps are closed, since
# deleting a team or a stage now always closes the gap it leaves. A formula
# names a stage by its place in the list, not its value, so no formula
# changes. A team not yet placed in a division is in no list and is left
# alone.
#
# This is its own migration because PostgreSQL will not alter a table in the
# transaction that has updated its rows.

from django.db import migrations


def renumber(model):
    divisions = (
        model.objects.filter(division__isnull=False)
        .order_by()
        .values_list("division_id", flat=True)
        .distinct()
    )
    for division_id in divisions:
        rows = list(
            model.objects.filter(division_id=division_id).order_by("order", "pk")
        )
        if [row.order for row in rows] == list(range(1, len(rows) + 1)):
            continue
        # Two passes keep every value distinct along the way.
        offset = max(row.order for row in rows)
        for n, row in enumerate(rows, 1):
            model.objects.filter(pk=row.pk).update(order=offset + n)
        for n, row in enumerate(rows, 1):
            model.objects.filter(pk=row.pk).update(order=n)


def forwards(apps, schema_editor):
    renumber(apps.get_model("competition", "Team"))
    renumber(apps.get_model("competition", "Stage"))


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0071_unique_order"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
