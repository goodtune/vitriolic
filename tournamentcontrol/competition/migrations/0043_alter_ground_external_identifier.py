from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0042_ground_external_identifier"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ground",
            name="external_identifier",
            field=models.CharField(
                blank=True, db_index=True, max_length=50, null=True, unique=True
            ),
        ),
    ]
