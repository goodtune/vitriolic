# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0002_sitemapnode_last_modified'),
    ]

    operations = [
        migrations.DeleteModel(
            name='PythonPackage',
        ),
        migrations.AlterModelOptions(
            name='sitemapnode',
            options={'verbose_name': 'folder', 'ordering': ('tree_id', 'lft')},
        ),
    ]
