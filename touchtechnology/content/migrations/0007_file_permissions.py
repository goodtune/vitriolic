# The media section's views take two permissions of the content app over the
# site's files, which have no model of their own: the pages hold them. This
# alters no table; Django adds the permission rows after migrating.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0006_list_ordering"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="page",
            options={
                "permissions": [
                    ("view_file", "Can view files"),
                    ("delete_file", "Can delete files"),
                ]
            },
        ),
    ]
