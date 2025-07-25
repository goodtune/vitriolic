from dataclasses import dataclass

from django.urls import reverse_lazy
from django.utils.functional import cached_property


@dataclass
class AdminUrlLookup:
    url_name: str
    args: tuple


class AdminUrlMixin(object):
    """
    Mixin which can be used to add API to a model for use by standard admin
    component templates, tags, and filters.
    """

    def _get_admin_namespace(self):
        raise NotImplementedError

    def _get_url_args(self):
        raise NotImplementedError

    def _get_url_names(self):
        # Default view names - extend on your model to add extra views
        return ["add", "edit", "delete", "perms"]

    @cached_property
    def urls(self):
        return {
            view: reverse_lazy(lookup.url_name, args=lookup.args)
            for view, lookup in self.url_names.items()
        }

    @cached_property
    def url_names(self) -> dict[str, AdminUrlLookup]:
        namespace = self._get_admin_namespace()
        args = self._get_url_args()
        crud = {
            name: AdminUrlLookup(
                url_name=f"{namespace}:{name}",
                args=[each for each in args if each is not None],
            )
            for name in self._get_url_names()
        }
        return crud
