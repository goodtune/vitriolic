# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import touchtechnology.common.db.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Chunk",
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
                ("slug", models.SlugField(verbose_name="Slug")),
                (
                    "copy",
                    touchtechnology.common.db.models.HTMLField(
                        verbose_name="Page Copy", blank=True
                    ),
                ),
            ],
            options={},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="Content",
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
                ("copy", touchtechnology.common.db.models.HTMLField(blank=True)),
            ],
            options={},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="NodeContent",
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
                    "copy",
                    touchtechnology.common.db.models.HTMLField(
                        verbose_name="Page Copy", blank=True
                    ),
                ),
                (
                    "node",
                    models.ForeignKey(
                        related_name="contents",
                        verbose_name="Node",
                        to="common.SitemapNode",
                        on_delete=models.PROTECT,
                    ),
                ),
            ],
            options={},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="Page",
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
                    "template",
                    touchtechnology.common.db.models.TemplatePathField(
                        max_length=200, verbose_name="Template", blank=True
                    ),
                ),
                (
                    "keywords",
                    models.CharField(
                        help_text="This should be a comma-separated list of terms that indicate the content of this page - used to assist Search Engines rank your page.",
                        max_length=255,
                        verbose_name="Keywords",
                        blank=True,
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        help_text="Search Engines may use this when determining the relevance of your page.",
                        max_length=255,
                        verbose_name="Description",
                        blank=True,
                    ),
                ),
            ],
            options={},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="PageContent",
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
                        default="copy",
                        max_length=20,
                        verbose_name="CSS class",
                        choices=[(b"copy", b"copy")],
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
                    "page",
                    models.ForeignKey(
                        related_name="content",
                        verbose_name="Page",
                        to="content.Page",
                        on_delete=models.PROTECT,
                    ),
                ),
            ],
            options={"ordering": ("sequence",),},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="Placeholder",
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
                ("path", models.CharField(max_length=255, verbose_name="Module path")),
                (
                    "namespace",
                    models.CharField(
                        max_length=255, verbose_name="Namespace", db_index=True
                    ),
                ),
            ],
            options={},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="PlaceholderKeywordArgument",
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
                ("key", models.CharField(max_length=200, verbose_name="Key")),
                (
                    "value",
                    models.TextField(
                        default="null",
                        help_text="Enter a valid JSON object",
                        verbose_name="Value",
                        blank=True,
                    ),
                ),
                (
                    "node",
                    models.ForeignKey(
                        related_name="kw",
                        verbose_name="Node",
                        to="common.SitemapNode",
                        on_delete=models.PROTECT,
                    ),
                ),
            ],
            options={},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="Redirect",
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
                    "source_url",
                    models.CharField(
                        help_text="The path that will trigger the redirection.",
                        max_length=250,
                        verbose_name="Source URL",
                    ),
                ),
                (
                    "destination_url",
                    models.CharField(
                        help_text="The URL or path that the browser will be sent to.",
                        max_length=500,
                        verbose_name="Destination URL",
                    ),
                ),
                (
                    "label",
                    models.CharField(max_length=100, verbose_name="Label", blank=True),
                ),
                ("active", models.BooleanField(default=True, verbose_name="Active")),
                (
                    "permanent",
                    models.BooleanField(default=False, verbose_name="Permanent"),
                ),
            ],
            options={"ordering": ("destination_url",),},
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name="placeholderkeywordargument", unique_together=set([("node", "key")]),
        ),
    ]
