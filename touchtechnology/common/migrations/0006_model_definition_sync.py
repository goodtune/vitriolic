# -*- coding: utf-8 -*-

from django.db import migrations, models

import touchtechnology.common.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0005_sitemapnode_populate_kwargs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitemapnode",
            name="enabled",
            field=touchtechnology.common.db.models.BooleanField(
                default=True,
                help_text="Set this to 'No' to disable this object and it's children on the site.",
                verbose_name="Enabled",
            ),
        ),
        migrations.AlterField(
            model_name="sitemapnode",
            name="hidden_from_navigation",
            field=touchtechnology.common.db.models.BooleanField(
                default=False,
                help_text="When set to 'Yes' this object will still be available, but will not appear in menus.",
                verbose_name="Hide from menus",
            ),
        ),
        migrations.AlterField(
            model_name="sitemapnode",
            name="hidden_from_robots",
            field=touchtechnology.common.db.models.BooleanField(
                default=False,
                help_text="Set this to <em>Yes</em> to prevent search engines from indexing this part of the site.<br><strong>Warning:</strong> this may affect your ranking in search engines.",
                verbose_name="Hide from spiders",
            ),
        ),
        migrations.AlterField(
            model_name="sitemapnode",
            name="hidden_from_sitemap",
            field=touchtechnology.common.db.models.BooleanField(
                default=False,
                help_text="When set to 'Yes' this object will not be listed in the auto-generated sitemap.",
                verbose_name="Hide from sitemap",
            ),
        ),
        migrations.AlterField(
            model_name="sitemapnode",
            name="last_modified",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="sitemapnode",
            name="require_https",
            field=touchtechnology.common.db.models.BooleanField(
                default=False,
                help_text="Force this to be served via HTTPS.",
                verbose_name="HTTPS Required",
            ),
        ),
        migrations.AlterField(
            model_name="sitemapnode",
            name="restrict_to_groups",
            field=models.ManyToManyField(
                blank=True,
                help_text="If you select one or more of these groups your visitors will need to be logged in and a member of an appropriate group to view this part of the site.",
                to="auth.Group",
                verbose_name="Restrict to Groups",
            ),
        ),
        migrations.AlterField(
            model_name="sitemapnode",
            name="slug_locked",
            field=touchtechnology.common.db.models.BooleanField(
                default=False, verbose_name="Slug locked"
            ),
        ),
    ]
