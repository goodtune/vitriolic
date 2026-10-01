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
        lft, rght, level) to avoid database queries. Uses ``parent_id``
        (the raw FK column) to avoid triggering lazy loads; falls back
        to ``getattr(node, "parent_id", None)`` so that ``FauxNode``
        (which only carries ``parent``) works too.
        """
        from .models import SitemapNode
        from .utils import FauxNode

        def _parent_id(node):
            pid = getattr(node, "parent_id", None)
            if pid is None:
                parent = getattr(node, "parent", None)
                if parent is not None:
                    pid = getattr(parent, "pk", None)
            return pid

        if other == self:
            return "ME"

        if _parent_id(other) is None:
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

        self_pid = _parent_id(self)
        other_pid = _parent_id(other)

        if self_pid == other_pid:
            return "SIBLING"

        if self_pid is not None and other_pid is not None:
            if other.level == self.level - 1 and other_pid != self_pid:
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
