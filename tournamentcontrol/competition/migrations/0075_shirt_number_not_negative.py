import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("competition", "0074_season_commentate_permission")]

    operations = [
        migrations.AlterField(
            model_name="simplescorematchstatistic",
            name="number",
            field=models.IntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
        migrations.AlterField(
            model_name="teamassociation",
            name="number",
            field=models.IntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]
