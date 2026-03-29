from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0009_translation"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="translation",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="translation",
            constraint=models.UniqueConstraint(
                fields=["article", "locale"],
                name="news_translation_unique_article_locale",
            ),
        ),
    ]
