"""
[Developer API] Where an admin page sits, and how to jump to any object.

The console admin knows the hierarchy of a deployment without being told: every
model with ``AdminUrlMixin`` names its admin namespace, and the admin's URLs
nest the way the objects do (``competition/1/seasons/2/division/4/``). From
those two facts this module builds

* the *trail* of a page, the chain of pages above it, each a link, so the
  person always sees where they are and can move up any number of levels; and
* the *jump* search, which finds an object of any model by its name and opens
  its edit page, wherever it sits in the hierarchy.

Neither needs a deployment to register anything: its own components and models
are found the same way as vitriolic's.
"""

import logging
import operator
from dataclasses import dataclass
from functools import cache, reduce

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import models
from django.db.models import Q
from django.urls import NoReverseMatch, Resolver404, resolve, reverse
from django.utils.encoding import smart_str
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _

from touchtechnology.admin.mixins import AdminUrlMixin

logger = logging.getLogger(__name__)

#: The text fields a jump search looks in, where a model has them.
SEARCH_FIELDS = (
    "title",
    "name",
    "headline",
    "label",
    "short_title",
    "first_name",
    "last_name",
    "abbreviation",
    "source_url",
)

#: How many objects of one kind a jump search returns.
JUMP_PER_MODEL = 6

#: The keyword arguments a resolved admin URL carries that are not keys.
NOT_KEYS = {"admin", "component", "cls"}


@dataclass(frozen=True)
class Crumb:
    """One step of a trail: what it is, what it is called, and where it is."""

    kind: str
    label: str
    url: str


@dataclass(frozen=True)
class Hit:
    """One object a jump search found."""

    kind: str
    label: str
    url: str
    context: str


@cache
def registry():
    """
    Every concrete model with ``AdminUrlMixin``, by its admin namespace.

    The namespace is a property of the class, but the mixin asks an instance
    for it, so an unsaved instance is made to ask. A model whose namespace
    cannot be worked out that way is left out.
    """
    found = {}
    for model in apps.get_models():
        if not issubclass(model, AdminUrlMixin) or model._meta.abstract:
            continue
        try:
            namespace = model()._get_admin_namespace()
        except Exception:  # noqa: BLE001 - a model that needs state is skipped
            logger.debug("no admin namespace for %s", model._meta.label)
            continue
        found.setdefault(namespace, model)
    return found


def model_for(namespace):
    """
    The model of an admin namespace. A namespace that nests a model somewhere
    else (a team's matches) is matched by its last part, the model's name.
    """
    known = registry()
    if namespace in known:
        return known[namespace]
    last = namespace.rsplit(":", 1)[-1]
    for model in known.values():
        if model._meta.model_name == last:
            return model
    return None


def _key(kwargs):
    """The key of the object an edit URL names: ``pk``, or its innermost id."""
    if "pk" in kwargs:
        return kwargs["pk"]
    keys = [k for k in kwargs if k not in NOT_KEYS and k.endswith("_id")]
    return kwargs[keys[-1]] if keys else None


def _describe(match, url, known=None):
    """
    The crumb of one resolved admin URL, or ``None`` when it is not a page.
    ``known`` maps ``(model, str(pk))`` to objects the page already has, so a
    crumb for one of them costs no query.
    """
    name = match.url_name
    namespace = match.namespace
    if namespace == "admin" and name == "index":
        return Crumb("", smart_str(_("Dashboard")), url)
    component = match.kwargs.get("component")
    if name == "index" and component is not None:
        # A component is a step of the trail only when its index is a page of
        # its own; most only redirect to their first list, which the trail
        # names anyway.
        if namespace.count(":") == 1 and getattr(component, "index_page", False):
            return Crumb("", smart_str(component.verbose_name), url)
        return None
    model = model_for(namespace)
    if model is None:
        return None
    if name == "list":
        return Crumb("", capfirst(smart_str(model._meta.verbose_name_plural)), url)
    if name == "edit":
        key = _key(match.kwargs)
        if key is None:
            return None
        obj = (known or {}).get((model, str(key)))
        if obj is None:
            try:
                obj = model._default_manager.filter(pk=key).first()
            except (ValueError, TypeError):
                obj = None
        if obj is None:
            return None
        return Crumb(capfirst(smart_str(model._meta.verbose_name)), smart_str(obj), url)
    return None


def trail(path, known=None):
    """
    The pages above ``path``, outermost first: each shorter prefix of the path
    that is itself an admin page, as a ``Crumb``. The page itself is not in it.
    """
    parts = [p for p in path.split("/") if p]
    crumbs = []
    for n in range(1, len(parts)):
        prefix = "/" + "/".join(parts[:n]) + "/"
        try:
            match = resolve(prefix)
        except Resolver404:
            continue
        crumb = _describe(match, prefix, known)
        if crumb is not None:
            crumbs.append(crumb)
    return crumbs


def parent_of(obj):
    """
    The object ``obj`` is listed under: the object its foreign key points to
    whose model owns the namespace one level above its own.
    """
    try:
        namespace = obj._get_admin_namespace()
    except Exception:  # noqa: BLE001
        return None
    parent_model = model_for(namespace.rsplit(":", 1)[0])
    if parent_model is None:
        return None
    for field in obj._meta.get_fields():
        if (
            isinstance(field, models.ForeignKey)
            and field.related_model is not None
            and issubclass(parent_model, field.related_model)
        ):
            try:
                return getattr(obj, field.name)
            except Exception:  # noqa: BLE001 - an unsaved object has no parent
                return None
    return None


def context_of(obj, depth=2):
    """Where ``obj`` sits, as the names of up to ``depth`` of its parents."""
    names = []
    parent = parent_of(obj)
    while parent is not None and len(names) < depth:
        names.append(smart_str(parent))
        parent = parent_of(parent)
    return " · ".join(names)


def _fields(model):
    return [
        f.name
        for f in model._meta.get_fields()
        if f.name in SEARCH_FIELDS and isinstance(f, models.CharField) and not f.choices
    ]


def _matching(fields, words):
    """Every word in at least one of the fields."""
    return reduce(
        operator.and_,
        (
            reduce(operator.or_, (Q(**{f"{f}__icontains": word}) for f in fields))
            for word in words
        ),
    )


def _may_see(user, model):
    if user.is_superuser:
        return True
    label = model._meta.app_label
    name = model._meta.model_name
    return user.has_perm(f"{label}.change_{name}") or user.has_perm(
        f"{label}.view_{name}"
    )


def _edit_url(obj):
    try:
        return str(obj.urls["edit"])
    except (KeyError, NoReverseMatch, AttributeError, TypeError, ValueError):
        return ""


def jump(user, query):
    """
    The objects whose names contain every word of ``query``, of every model
    the person may change, grouped by kind: a list of ``(kind, [Hit, ...])``.
    """
    words = query.split()
    if not words:
        return []
    groups = []
    seen = set()
    for model in registry().values():
        if model in seen:
            continue
        seen.add(model)
        fields = _fields(model)
        if not fields or not _may_see(user, model):
            continue
        hits = []
        for obj in model._default_manager.filter(_matching(fields, words))[
            :JUMP_PER_MODEL
        ]:
            url = _edit_url(obj)
            if url:
                hits.append(
                    Hit(
                        capfirst(smart_str(model._meta.verbose_name)),
                        smart_str(obj),
                        url,
                        context_of(obj),
                    )
                )
        if hits:
            groups.append((capfirst(smart_str(model._meta.verbose_name_plural)), hits))
    groups.extend(_auth_hits(user, words))
    return groups


def _auth_hits(user, words):
    """Accounts and groups, which have no ``AdminUrlMixin`` of their own."""
    groups = []
    User = get_user_model()
    if _may_see(user, User):
        fields = [
            f
            for f in ("first_name", "last_name", "email", User.USERNAME_FIELD)
            if any(field.name == f for field in User._meta.get_fields())
        ]
        hits = [
            Hit(
                smart_str(_("User")),
                u.get_full_name() or u.get_username(),
                reverse("admin:auth:users:edit", args=[u.pk]),
                u.email,
            )
            for u in User.objects.filter(_matching(fields, words))[:JUMP_PER_MODEL]
        ]
        if hits:
            groups.append((smart_str(_("Users")), hits))
    if _may_see(user, Group):
        hits = [
            Hit(
                smart_str(_("Group")),
                g.name,
                reverse("admin:auth:groups:edit", args=[g.pk]),
                "",
            )
            for g in Group.objects.filter(_matching(["name"], words))[:JUMP_PER_MODEL]
        ]
        if hits:
            groups.append((smart_str(_("Groups")), hits))
    return groups


def sections(components):
    """
    The places a person can go from the menu, as ``(component, label, url)``,
    from the components the person may use (``allowed`` has filtered them).
    """
    found = []
    for verbose_name, __, url, component, __ in components:
        if not component.visible:
            continue
        dropdowns = list(component.dropdowns() or ())
        if not dropdowns:
            found.append((verbose_name, verbose_name, str(url)))
        for item in dropdowns:
            found.append((verbose_name, smart_str(item[0]), str(item[1])))
    return found
