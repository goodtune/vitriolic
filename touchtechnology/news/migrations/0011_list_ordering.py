# The admin shows the categories, and an article's translations, a page at a
# time, and a list in no order may show an object on two pages or on none. It
# alters no table and issues no SQL.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0010_migrate_unique_together_to_constraints"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="category",
            options={"ordering": ("title",), "verbose_name_plural": "categories"},
        ),
        migrations.AlterModelOptions(
            name="translation",
            options={"ordering": ("locale",)},
        ),
    ]
