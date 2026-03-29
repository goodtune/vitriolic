# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('competition', '0059_division_color_unique_per_season'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='division',
            unique_together={('title', 'season'), ('slug', 'season'), ('season', 'color')},
        ),
    ]
