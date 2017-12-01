from __future__ import unicode_literals


class NodeRelationMixin(object):
    """
    A mixin to allow a Node subclass to determine the type of
    relationship it has with another. Used by the ``navigation``
    template tag.
    """
    def rel(self, other):
        """
        Returns the relationship as an uppercase string. Allowed values
        are as follows:

         * ME
         * ROOT
         * PARENT
         * ANCESTOR
         * SIBLING (share the same parent)
         * UNCLE (sibling of parent)
         * DESCENDANT

        For nodes that do not have a direct relationship, the value
        returned is generic dependant upon the type of instance - used
        only for debugging purposes.

         * SITEMAP
         * FAUX
        """
        from .models import SitemapNode
        from .utils import FauxNode

        if other == self:
            return 'ME'

        if self.parent and other == self.parent:
            return 'PARENT'

        if other.parent == self.parent:
            return 'SIBLING'

        if other.parent and other.parent == self:
            return 'DESCENDANT'

        if self.parent:
            prel = self.parent.rel(other)

            if prel == 'SIBLING':
                return 'UNCLE'

            if prel == 'PARENT':
                return 'ANCESTOR'

            if prel == 'ANCESTOR':
                return prel

        if other.parent is None:
            return 'ROOT'

        if other.tree_id == self.tree_id:
            if other.level < self.level:
                return 'ANCESTOR'

        if isinstance(other, SitemapNode):
            return 'SITEMAP'
        if isinstance(other, FauxNode):
            return 'FAUX'

        raise ValueError('You must provide a "SitemapNode" or '
                         '"FauxNode" for comparison.')
