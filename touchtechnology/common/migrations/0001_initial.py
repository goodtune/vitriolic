# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import touchtechnology.common.db.models
import touchtechnology.common.mixins


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0001_initial'),
        ('contenttypes', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PythonPackage',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('version', models.CharField(max_length=20)),
                ('latest', models.CharField(max_length=20)),
                ('active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ('name',),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='SitemapNode',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=255, verbose_name='Title')),
                ('short_title', models.CharField(help_text='This is used in navigation menus instead of the longer title value.', max_length=100, verbose_name='Short title', blank=True)),
                ('slug', models.SlugField(max_length=255, verbose_name='Slug')),
                ('slug_locked', touchtechnology.common.db.models.BooleanField(default=False, verbose_name='Slug locked')),
                ('object_id', models.PositiveIntegerField(null=True, blank=True)),
                ('require_https', touchtechnology.common.db.models.BooleanField(default=False, help_text='Force this to be served via HTTPS.', verbose_name='HTTPS Required')),
                ('enabled', touchtechnology.common.db.models.BooleanField(default=True, help_text="Set this to 'No' to disable this object and it's children on the site.", verbose_name='Enabled')),
                ('hidden_from_navigation', touchtechnology.common.db.models.BooleanField(default=False, help_text="When set to 'Yes' this object will still be available, but will not appear in menus.", verbose_name='Hide from menus')),
                ('hidden_from_sitemap', touchtechnology.common.db.models.BooleanField(default=False, help_text="When set to 'Yes' this object will not be listed in the auto-generated sitemap.", verbose_name='Hide from sitemap')),
                ('hidden_from_robots', touchtechnology.common.db.models.BooleanField(default=False, help_text="Set this to 'Yes' to prevent search engines from indexing this part of the site.<br />\n<strong>Warning:</strong> this may affect your ranking in search engines.", verbose_name='Hide from spiders')),
                ('lft', models.PositiveIntegerField(editable=False, db_index=True)),
                ('rght', models.PositiveIntegerField(editable=False, db_index=True)),
                ('tree_id', models.PositiveIntegerField(editable=False, db_index=True)),
                ('level', models.PositiveIntegerField(editable=False, db_index=True)),
                ('content_type', models.ForeignKey(blank=True, to='contenttypes.ContentType', null=True)),
                ('parent', touchtechnology.common.db.models.TreeField(related_name=b'children', verbose_name='Parent', blank=True, to='common.SitemapNode', null=True)),
                ('restrict_to_groups', touchtechnology.common.db.models.ManyToManyField(help_text='If you select one or more of these groups your visitors will need to be logged in and a member of an appropriate group to view this part of the site.', to='auth.Group', verbose_name='Restrict to Groups', blank=True)),
            ],
            options={
                'ordering': ('tree_id', 'lft'),
            },
            bases=(touchtechnology.common.mixins.NodeRelationMixin, models.Model),
        ),
    ]
