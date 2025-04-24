from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0036_auto_20191122_1340"),
    ]

    operations = [
        migrations.AlterField(
            model_name="match",
            name="evaluated",
            field=models.BooleanField(null=True),
        ),
    ]
