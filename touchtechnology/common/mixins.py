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

        Relationships are determined using MPTT tree fields (tree_id,
        lft, rght, level) to avoid database queries.
        """
        from .models import SitemapNode
        from .utils import FauxNode

        if other == self:
            return "ME"

        if other.parent_id is None:
            return "ROOT"

        if other.tree_id != self.tree_id:
            if isinstance(other, SitemapNode):
                return "SITEMAP"
            if isinstance(other, FauxNode):
                return "FAUX"
            raise ValueError(
                'You must provide a "SitemapNode" or "FauxNode" for comparison.'
            )

        # Same tree — use MPTT fields to determine relationship.
        is_ancestor = other.lft < self.lft and other.rght > self.rght
        if is_ancestor:
            if other.level == self.level - 1:
                return "PARENT"
            return "ANCESTOR"

        if other.lft > self.lft and other.rght < self.rght:
            return "DESCENDANT"

        if self.parent_id == other.parent_id:
            return "SIBLING"

        if self.parent_id is not None and other.parent_id is not None:
            # Check if other is a sibling of self's direct parent. Use
            # MPTT fields to identify the parent's boundaries: the parent
            # is the ancestor at level - 1 whose lft/rght enclose self.
            # If other shares that same parent_id, it's an uncle.
            if other.level == self.level - 1 and other.parent_id != self.parent_id:
                return "UNCLE"

        if other.level < self.level:
            return "ANCESTOR"

        if isinstance(other, SitemapNode):
            return "SITEMAP"
        if isinstance(other, FauxNode):
            return "FAUX"

        raise ValueError(
            'You must provide a "SitemapNode" or "FauxNode" for comparison.'
        )
