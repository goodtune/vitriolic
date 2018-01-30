from django.contrib.sitemaps import Sitemap
from django.db.models import Q
from touchtechnology.common.models import SitemapNode
from touchtechnology.common.utils import create_exclude_filter


class NodeSitemap(Sitemap):

    def items(self):
        nodes = SitemapNode._tree_manager.select_related('content_type')

        nodes_hidden_from_sitemap = nodes.filter(
            Q(hidden_from_sitemap=True) | Q(enabled=False))
        hidden_from_sitemap = create_exclude_filter(nodes_hidden_from_sitemap)
        nodes = nodes.exclude(hidden_from_sitemap)

        nodes = nodes.order_by('tree_id', 'lft')

        # flatten the list of nodes to a list
        tree = list(nodes)

        # insert faux SitemapNode objects into the tree where possible
        placeholders = nodes.filter(content_type__app_label='content',
                                    content_type__model='placeholder')
        for app_node in sorted(placeholders, reverse=True):
            site = app_node.object.site(app_node)
            if hasattr(site, 'sitemapnodes'):
                index = tree.index(app_node) + 1
                tree = tree[:index] + list(site.sitemapnodes()) + tree[index:]

        return tree

    def priority(self, obj):
        if hasattr(obj, 'priority'):
            return getattr(obj, 'priority')
        return 0.5

    def changefreq(self, obj):
        if hasattr(obj, 'changefreq'):
            return getattr(obj, 'changefreq')
        return 'weekly'
