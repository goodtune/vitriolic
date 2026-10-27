# A division's teams are kept numbered 1, 2, 3, ...: deleting or regrading a
# team closes the gap it leaves, in two passes the database can check row by
# row. Two teams of a division may not share a value, as two stages may not
# since 0071. Teams were renumbered by 0072.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0072_dense_orders"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="team",
            constraint=models.UniqueConstraint(
                fields=["division", "order"],
                name="competition_team_unique_division_order",
            ),
        ),
    ]
