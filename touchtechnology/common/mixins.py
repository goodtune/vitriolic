from django.forms import widgets


class BootstrapFormControlMixin(object):
    """
    Twitter bootstrap is the most widely used user-interface framework. Many
    designers will have experience with it, and there are numerous off-shelf
    themes being built for marketplaces that leverage bootstrap.

    This mixin should be applied to all forms. It will add placeholder text and
    set the bootstrap "form-control" class to the widget of the field.
    """
    def __init__(self, *args, **kwargs):
        super(BootstrapFormControlMixin, self).__init__(*args, **kwargs)
        for field_name in getattr(self, 'fields', ()):
            field = self.fields[field_name]

            # Which widget types don't we want to have the placeholder
            # overloaded with the title?
            if not isinstance(field.widget, (widgets.RadioSelect,
                                             widgets.MultiWidget)):
                field.widget.attrs.setdefault('placeholder', field.label)

            # Which widget types don't we want to have the class attribute set
            # to be 'form-control'?
            if not isinstance(field.widget, (widgets.RadioSelect,)):
                field.widget.attrs['class'] = 'form-control'


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

        raise ValueError(u'You must provide a "SitemapNode" or '
                         u'"FauxNode" for comparison.')
