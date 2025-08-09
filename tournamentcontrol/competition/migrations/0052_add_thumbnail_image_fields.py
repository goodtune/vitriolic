from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0051_plpgsql_vitriolic_stage_group_position"),
    ]

    operations = [
        migrations.AddField(
            model_name="season",
            name="thumbnail_image",
            field=models.BinaryField(
                blank=True,
                null=True,
                help_text="Binary data for thumbnail image to be used for YouTube videos",
            ),
        ),
        migrations.AddField(
            model_name="match",
            name="thumbnail_image",
            field=models.BinaryField(
                blank=True,
                null=True,
                help_text="Binary data for thumbnail image to be used for YouTube video",
            ),
        ),
    ]