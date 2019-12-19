from django.db import migrations


def article_content_to_copy(apps, schema_editor):
    Article = apps.get_model("news", "Article")

    for article in Article.objects.prefetch_related("content"):
        article.copy = "\n".join(
            [
                "<!-- %(label)s -->\n%(copy)s\n<!-- /%(label)s -->\n" % data
                for data in article.content.values()
            ]
        )
        article.save()


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0006_article_copy_field"),
    ]

    operations = [
        migrations.RunPython(
            article_content_to_copy, reverse_code=migrations.RunPython.noop
        )
    ]
