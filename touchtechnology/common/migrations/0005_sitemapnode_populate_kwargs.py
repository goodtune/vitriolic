# -*- coding: utf-8 -*-

import json

from django.db import migrations


def populate_kwargs(apps, schema_editor):
    SitemapNode = apps.get_model("common", "SitemapNode")
    for node in SitemapNode.objects.all():
        data = {
            key: json.loads(value) for key, value in node.kw.values_list("key", "value")
        }
        if data:
            node.kwargs = data
            node.save()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0004_sitemapnode_kwargs"),
    ]

    operations = [
        migrations.RunPython(populate_kwargs, noop),
    ]
