# Generated by Django 3.2.13 on 2022-07-30 13:43

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0045_ground_stream_key"),
    ]

    operations = [
        migrations.AlterField(
            model_name="match",
            name="live_stream_bind",
            field=models.CharField(blank=True, db_index=True, max_length=50, null=True),
        ),
    ]
