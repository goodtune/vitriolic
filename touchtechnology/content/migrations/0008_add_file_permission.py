# The media section's upload and new folder, the POST of its list, take a third
# permission of the content app over the site's files, held by the pages like
# the two before it. This alters no table; Django adds the permission row after
# migrating.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0007_file_permissions"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="page",
            options={
                "permissions": [
                    ("add_file", "Can add files"),
                    ("view_file", "Can view files"),
                    ("delete_file", "Can delete files"),
                ]
            },
        ),
    ]
