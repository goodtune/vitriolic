# The help_text on the thumbnail image fields was reworded in the models without
# a migration to record it, so makemigrations kept proposing this change. It
# alters no column and issues no SQL.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0067_remove_mysideline"),
    ]

    operations = [
        migrations.AlterField(
            model_name="season",
            name="live_stream_thumbnail_image",
            field=models.BinaryField(
                blank=True,
                editable=True,
                help_text="Image to be used as thumbnail image on the YouTube platform",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="match",
            name="live_stream_thumbnail_image",
            field=models.BinaryField(
                blank=True,
                editable=True,
                help_text="Image to be used as thumbnail image on the YouTube platform",
                null=True,
            ),
        ),
    ]
