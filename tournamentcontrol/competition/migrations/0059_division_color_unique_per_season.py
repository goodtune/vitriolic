# Migration to add uniqueness constraint for Division color within a Season

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0058_populate_color_fields"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="division",
            constraint=models.UniqueConstraint(
                fields=["season", "color"],
                name="division_color_unique_per_season",
            ),
        ),
    ]
