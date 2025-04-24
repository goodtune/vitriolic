from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0041_ground_live_stream"),
    ]

    operations = [
        migrations.AddField(
            model_name="ground",
            name="external_identifier",
            field=models.CharField(
                blank=True, db_index=True, max_length=20, null=True, unique=True
            ),
        ),
    ]
