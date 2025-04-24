from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0006_model_definition_sync"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitemapnode",
            name="kwargs",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="sitemapnode",
            name="level",
            field=models.PositiveIntegerField(editable=False),
        ),
        migrations.AlterField(
            model_name="sitemapnode",
            name="lft",
            field=models.PositiveIntegerField(editable=False),
        ),
        migrations.AlterField(
            model_name="sitemapnode",
            name="rght",
            field=models.PositiveIntegerField(editable=False),
        ),
    ]
