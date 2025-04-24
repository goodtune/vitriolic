# -*- coding: utf-8 -*-

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0003_auto_20160831_0608"),
        ("common", "0005_sitemapnode_populate_kwargs"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="placeholderkeywordargument",
            unique_together=set([]),
        ),
        migrations.RemoveField(
            model_name="placeholderkeywordargument",
            name="node",
        ),
        migrations.DeleteModel(
            name="PlaceholderKeywordArgument",
        ),
    ]
