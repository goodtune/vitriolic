# The admin shows the tabs of a season (time slots), a division (exclusion
# dates) and a match (ladder entries and score sheets) a page at a time, and a
# list in no order may show an object on two pages or on none. A division's
# exclusion dates now take their order from ExclusionDateBase, as a season's
# always have. It alters no table and issues no SQL.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0068_thumbnail_image_help_text"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="divisionexclusiondate",
            options={"ordering": ("date",), "verbose_name": "exclusion date"},
        ),
        migrations.AlterModelOptions(
            name="ladderentry",
            options={"ordering": ("pk",)},
        ),
        migrations.AlterModelOptions(
            name="matchscoresheet",
            options={"ordering": ("pk",)},
        ),
        migrations.AlterModelOptions(
            name="seasonmatchtime",
            options={"ordering": ("start",), "verbose_name": "time slot"},
        ),
    ]
