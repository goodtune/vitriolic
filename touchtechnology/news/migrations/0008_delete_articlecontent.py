from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0007_article_copy_field_data"),
    ]

    operations = [
        migrations.DeleteModel(name="ArticleContent",),
    ]
