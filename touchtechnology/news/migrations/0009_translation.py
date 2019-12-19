import django.db.models.deletion
from django.db import migrations, models

import touchtechnology.admin.mixins
import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0008_delete_articlecontent"),
    ]

    operations = [
        migrations.CreateModel(
            name="Translation",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("locale", models.CharField(max_length=10)),
                ("headline", models.CharField(max_length=150, verbose_name="Headline")),
                ("abstract", models.TextField(verbose_name="Abstract")),
                (
                    "copy",
                    touchtechnology.common.db.models.HTMLField(
                        blank=True, verbose_name="Copy"
                    ),
                ),
                (
                    "article",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="translations",
                        to="news.Article",
                    ),
                ),
            ],
            options={"unique_together": {("article", "locale")},},
            bases=(touchtechnology.admin.mixins.AdminUrlMixin, models.Model),
        ),
    ]
