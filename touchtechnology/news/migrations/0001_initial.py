# -*- coding: utf-8 -*-

from django.db import migrations, models

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Article",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                ("headline", models.CharField(max_length=150, verbose_name="Headline")),
                ("abstract", models.TextField(verbose_name="Abstract")),
                (
                    "published",
                    touchtechnology.common.db.models.DateTimeField(
                        help_text="Set a date & time in the future to schedule an announcement.",
                        verbose_name="Published",
                    ),
                ),
                ("slug", models.SlugField(max_length=150, verbose_name="Slug")),
                (
                    "slug_locked",
                    models.BooleanField(default=False, verbose_name="Locked Slug"),
                ),
                (
                    "byline",
                    models.CharField(max_length=75, verbose_name="Byline", blank=True),
                ),
                (
                    "keywords",
                    models.CharField(
                        max_length=255, verbose_name="Keywords", blank=True
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="Enabled"),
                ),
                (
                    "image",
                    models.ImageField(
                        upload_to="news", null=True, verbose_name="Image", blank=True
                    ),
                ),
            ],
            options={"ordering": ("-published",),},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="ArticleContent",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                (
                    "label",
                    models.SlugField(
                        max_length=20,
                        verbose_name="CSS class",
                        choices=[(b"copy", "Copy")],
                    ),
                ),
                ("sequence", models.PositiveIntegerField(verbose_name="Sequence")),
                (
                    "copy",
                    touchtechnology.common.db.models.HTMLField(
                        verbose_name="Copy", blank=True
                    ),
                ),
                (
                    "article",
                    models.ForeignKey(
                        related_name="content",
                        verbose_name="Article",
                        to="news.Article",
                        on_delete=models.PROTECT,
                    ),
                ),
            ],
            options={"ordering": ("sequence",),},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="Category",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                ("title", models.CharField(max_length=75, verbose_name="Title")),
                (
                    "short_title",
                    models.CharField(
                        help_text="Used in navigation, a shorter alternative to the main title.",
                        max_length=50,
                        verbose_name="Short Title",
                        blank=True,
                    ),
                ),
                ("slug", models.SlugField(max_length=75, verbose_name="Slug")),
                (
                    "slug_locked",
                    models.BooleanField(default=False, verbose_name="Locked Slug"),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="Enabled"),
                ),
                (
                    "hidden_from_navigation",
                    models.BooleanField(
                        default=False,
                        help_text="When set to 'Yes' this object will still be available, but will not appear in menus.",
                        verbose_name="Hide from menus",
                    ),
                ),
            ],
            options={},
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name="article",
            name="categories",
            field=models.ManyToManyField(
                to="news.Category", verbose_name="Categories", blank=True
            ),
            preserve_default=True,
        ),
    ]
