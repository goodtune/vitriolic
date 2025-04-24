from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0043_alter_ground_external_identifier"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="live_stream_bind",
            field=models.CharField(
                blank=True, db_index=True, max_length=50, null=True, unique=True
            ),
        ),
    ]
