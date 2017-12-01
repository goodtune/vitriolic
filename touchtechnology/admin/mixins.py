from django.urls import reverse_lazy
from django.utils.functional import cached_property


class AdminUrlMixin(object):
    """
    Mixin which can be used to add API to a model for use by standard admin
    component templates, tags, and filters.
    """

    def _get_admin_namespace(self):
        raise NotImplementedError

    def _get_url_args(self):
        raise NotImplementedError

    @cached_property
    def urls(self):
        namespace = self._get_admin_namespace()
        args = self._get_url_args()
        crud = {
            'edit': reverse_lazy(
                '%s:edit' % namespace, args=args),
            'delete': reverse_lazy(
                '%s:delete' % namespace, args=args),
            'perms': reverse_lazy(
                '%s:perms' % namespace, args=args),
        }
        return crud
