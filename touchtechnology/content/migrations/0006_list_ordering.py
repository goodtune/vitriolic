# The admin shows the chunks a page at a time, and a list in no order may show
# a chunk on two pages or on none. It alters no table and issues no SQL.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0005_model_definition_sync"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="chunk",
            options={"ordering": ("slug",)},
        ),
    ]
