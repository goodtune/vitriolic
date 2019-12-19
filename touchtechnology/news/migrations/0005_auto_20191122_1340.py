from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0004_model_definition_sync"),
    ]

    operations = [
        migrations.AlterField(
            model_name="articlecontent",
            name="label",
            field=models.SlugField(
                choices=[("copy", "Copy")], max_length=20, verbose_name="CSS class"
            ),
        ),
    ]
