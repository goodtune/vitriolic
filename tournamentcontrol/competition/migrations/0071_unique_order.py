# A formula names a stage by its number in the division's list (S1, S2, ...),
# and the list numbers the stages by ``order``, so two stages of a division
# may not share a value. A stage's pools have had the same constraint since
# 0059. Stages that shared a value were renumbered by 0070.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0070_renumber_shared_orders"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="stage",
            constraint=models.UniqueConstraint(
                fields=["division", "order"],
                name="competition_stage_unique_division_order",
            ),
        ),
    ]
