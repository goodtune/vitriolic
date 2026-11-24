"""
Where a page sits in the admin: the pages above it, found from its address.

Every admin address is nested under the address of the object it belongs to
(``/competition/1/seasons/2/division/4/`` is a division of season 2 of
competition 1), so the pages above a page are the prefixes of its address
that resolve to a page of their own. Each is named after the object it edits,
the list it shows, or the component it is the index of.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache

from django.apps import apps
from django.db.models import ForeignKey, Model
from django.urls import Resolver404, resolve
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _

from touchtechnology.admin.mixins import AdminUrlMixin

logger = logging.getLogger(__name__)

#: View names that never make a step of the trail.
SKIPPED = {"add", "delete", "perms", "bulk"}


@dataclass
class Crumb:
    label: str
    url: str
    model: type | None = None
    kind: str = ""


@lru_cache(maxsize=1)
def models_by_namespace():
    """Each URL namespace the admin's models report, and the model."""
    found = {}
    for model in apps.get_models():
        if not issubclass(model, AdminUrlMixin):
            continue
        try:
            namespace = model()._get_admin_namespace()
        except Exception:  # noqa: BLE001 - a model may need saved relations
            continue
        found.setdefault(namespace, model)
    return found


def tab_of(parent, child):
    """The tab of ``parent``'s edit page that lists ``child`` objects."""
    if parent is None or child is None:
        return ""
    for field in child._meta.get_fields():
        if isinstance(field, ForeignKey) and issubclass(parent, field.related_model):
            try:
                return f"#{field.remote_field.get_accessor_name()}-tab"
            except AttributeError:
                return ""
    return ""


def describe(match, url, site_name, known=None):
    """A crumb for the page ``match`` resolved ``url`` to, or ``None``."""
    if match.url_name in SKIPPED:
        return None
    if match.url_name == "index":
        if match.namespace == site_name:
            return Crumb(str(_("Home")), url)
        component = match.kwargs.get("component")
        if component is not None:
            return Crumb(str(component.verbose_name), url)
        return None
    model = models_by_namespace().get(match.namespace)
    if model is None:
        return None
    if match.url_name == "list":
        return Crumb(str(capfirst(model._meta.verbose_name_plural)), url, model)
    if match.url_name == "edit":
        keys = [
            value
            for key, value in match.kwargs.items()
            if key not in ("admin", "component")
        ]
        if not keys:
            return None
        instance = (known or {}).get((model, str(keys[-1])))
        if instance is None:
            instance = model._default_manager.filter(pk=keys[-1]).first()
        if instance is None:
            return None
        return Crumb(str(instance), url, model, "edit")
    return None


def build_trail(request, site_name="admin", context=None):
    """
    The pages above ``request``'s page, outermost first. Objects the page's
    ``context`` already holds are named from it rather than fetched again.
    """
    if request is None or getattr(request, "resolver_match", None) is None:
        return []
    path = request.path
    parts = [part for part in path.split("/") if part]
    known = {}
    for value in (context or {}).values():
        if isinstance(value, Model) and value.pk is not None:
            known[(type(value), str(value.pk))] = value
    crumbs = []
    for depth in range(1, len(parts)):
        prefix = "/" + "/".join(parts[:depth]) + "/"
        try:
            match = resolve(prefix)
        except Resolver404:
            continue
        if not match.namespace.split(":")[0] == site_name:
            continue
        try:
            crumb = describe(match, prefix, site_name, known)
        except Exception:  # noqa: BLE001 - a trail never breaks the page
            logger.exception("could not describe %s", prefix)
            crumb = None
        if crumb is not None:
            crumbs.append(crumb)

    # Link each object to the tab of its page that lists the next one down.
    here = models_by_namespace().get(request.resolver_match.namespace)
    for index, crumb in enumerate(crumbs):
        below = crumbs[index + 1].model if index + 1 < len(crumbs) else here
        if crumb.kind == "edit" and below is not None and below is not crumb.model:
            crumb.url = crumb.url + tab_of(crumb.model, below)
    return crumbs
