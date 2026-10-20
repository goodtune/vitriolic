"""
The explorer: the hierarchy of everything the admin manages, as a tree.

Every admin component is a top-level folder of the tree. Its sections (the
entries of its menu, from ``AdminComponent.dropdowns``) are the folders inside
it, and the objects behind them are found by following the admin's own URLs:

* an object belongs to the section whose URL its edit URL sits directly
  under (``/admin/fixja/competition/7/`` belongs to
  ``/admin/fixja/competition/``);
* an object's parent is the object, reached through one of its foreign keys,
  whose edit URL is the longest prefix of its own;
* an object's children are the one-to-many relations whose objects' edit URLs
  sit under its own.

So a deployment's component that nests its URLs, as the stock components do,
gets a tree without writing any code. A component may say more with
``Explorer`` subclass attributes (see ``AdminComponentMixin.explorer_class``):
which relations of a model are shown, under what label, whether they are a
folder of their own or listed directly, grouped by a field, and any custom
folders it can fill itself.

Nodes are identified by keys, so the browser can ask for the children of one
it has not been sent (``admin:explorer``). A key is ``<component>/<local>``
where the local part is one of:

``""``                                 the component itself
``s<n>``                               its n-th section
``o:<app>.<model>:<pk>``               an object
``g:<app>.<model>:<pk>:<rel>``         a relation of an object, as a folder
``g:<app>.<model>:<pk>:<rel>:<value>`` one group of that relation's objects
``x:<name>:<arg>``                     a node of the component's own making
"""

import logging
from dataclasses import dataclass, field

from django.apps import apps
from django.db import models
from django.urls import NoReverseMatch
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from guardian.shortcuts import get_objects_for_user

from touchtechnology.admin.mixins import AdminUrlMixin
from touchtechnology.common.utils import get_all_perms_for_model_cached

logger = logging.getLogger(__name__)

#: How many children a folder lists before it offers the rest as one link.
LIMIT = 40


@dataclass
class Node:
    key: str
    label: str
    url: str | None = None
    icon: str = "item"
    expandable: bool = False
    children: list | None = None
    open: bool = False
    current: bool = False
    on_trail: bool = False
    note: str = ""
    more: bool = False
    is_page: bool = False

    @property
    def dom_id(self):
        return "x-" + "".join(c if c.isalnum() else "-" for c in self.key)


@dataclass
class Rel:
    """
    One relation of a model, as the explorer shows it.

    ``name`` is the accessor of a one-to-many relation (``season.divisions``).
    ``flat`` lists its objects directly under their parent instead of in a
    folder of their own; by default a model with one relation is flat.
    ``group_by`` names a foreign key of the related model; the objects are
    then grouped in a folder per value (classes by grade).
    """

    name: str
    label: str | None = None
    flat: bool | None = None
    group_by: str | None = None
    icon: str | None = None


@dataclass
class Folder:
    """
    A folder of a model's objects that the component fills itself:
    ``children(explorer, request, obj)`` returns the nodes.
    """

    name: str
    label: str
    children: object = None
    icon: str = "folder"


def _url(obj, name="edit"):
    try:
        return str(obj.urls[name])
    except Exception:  # noqa: BLE001 - an object without that admin URL
        return None


def _key(obj):
    return "o:%s.%s:%s" % (obj._meta.app_label, obj._meta.model_name, obj.pk)


def _model_label(model):
    return "%s.%s" % (model._meta.app_label, model._meta.model_name)


def _has_admin_urls(model):
    return isinstance(model, type) and issubclass(model, AdminUrlMixin)


@dataclass
class _Section:
    label: str
    url: str
    icon: str
    model: type | None = None


class Explorer:
    """
    The tree of one admin component. Subclass it, and name the subclass on
    the component as ``explorer_class``, to say more than the URLs do.
    """

    #: model -> sequence of ``Rel`` or ``Folder``; a model not named here
    #: shows every relation whose objects nest under it.
    branches = {}
    #: model -> icon name, for the nodes of that model's objects.
    icons = {}
    #: section label -> icon name, for sections whose menu icon is not wanted.
    section_icons = {}

    _section_cache = {}
    _relation_cache = {}

    def __init__(self, component):
        self.component = component

    @property
    def shell(self):
        """The shell the component's admin wears, which names the icons."""
        return self.component.shell

    # ------------------------------------------------------------------
    # Keys

    @property
    def prefix(self):
        return self.component.name

    def key(self, local):
        return "%s/%s" % (self.prefix, local)

    # ------------------------------------------------------------------
    # Sections

    def sections(self):
        found = []
        for entry in self.component.dropdowns():
            label, url = entry[0], str(entry[1])
            model = self.section_model(url)
            found.append(
                _Section(
                    label=str(label),
                    url=url,
                    icon=self.section_icons.get(
                        str(label), self.shell.section_icon(entry, model)
                    ),
                    model=model,
                )
            )
        return found

    def section_model(self, url):
        """
        The model whose objects' edit URLs sit directly under ``url``. An
        unsaved instance with a primary key of 0 says where its edit URL
        would be; models nested under another need their parent to say, so
        they never qualify.
        """
        cache = Explorer._section_cache
        if url in cache:
            return cache[url]
        model = None
        for candidate in apps.get_models():
            if not _has_admin_urls(candidate):
                continue
            try:
                edit = str(candidate(pk=0).urls["edit"])
            except Exception:  # noqa: BLE001 - nested models cannot say
                continue
            if edit.startswith(url) and edit[len(url) :] == "0/":
                model = candidate
                break
        cache[url] = model
        return model

    def section_node(self, request, index, section):
        return Node(
            key=self.key("s%d" % index),
            label=section.label,
            url=section.url,
            icon=section.icon,
            expandable=section.model is not None,
        )

    # ------------------------------------------------------------------
    # Relations

    def relations(self, model, sample=None):
        """The ``Rel`` and ``Folder`` entries for ``model``'s children."""
        if model in self.branches:
            return list(self.branches[model])
        cache = Explorer._relation_cache
        if model not in cache:
            if sample is None:
                return []
            cache[model] = self.discover(model, sample)
        return cache[model]

    def discover(self, model, sample):
        """Every one-to-many relation of ``model`` whose objects nest under it."""
        parent_url = _url(sample)
        if not parent_url:
            return []
        found = []
        for rel in model._meta.get_fields():
            if not (rel.one_to_many and rel.auto_created):
                continue
            related = rel.related_model
            if not _has_admin_urls(related):
                continue
            try:
                child = related(**{rel.field.name: sample}, pk=0)
                child_url = str(child.urls["edit"])
            except Exception:  # noqa: BLE001 - not reachable this way
                continue
            if child_url.startswith(parent_url) and child_url != parent_url:
                found.append(Rel(rel.get_accessor_name()))
        return found

    def rel_label(self, model, rel):
        if rel.label:
            return str(rel.label)
        accessor = getattr(model, rel.name, None)
        related = getattr(getattr(accessor, "rel", None), "related_model", None)
        if related is not None:
            return capfirst(str(related._meta.verbose_name_plural))
        return capfirst(rel.name.replace("_", " "))

    def is_flat(self, model, rel, rels):
        if isinstance(rel, Folder):
            return False
        if rel.flat is not None:
            return rel.flat
        return len(rels) == 1 and not rel.group_by

    # ------------------------------------------------------------------
    # Nodes

    def object_label(self, obj):
        return str(obj)

    def object_note(self, obj):
        return ""

    def object_node(self, obj):
        model = type(obj)
        return Node(
            key=self.key(_key(obj)),
            label=self.object_label(obj),
            url=_url(obj),
            icon=self.icons.get(model, self.shell.model_icon(model)),
            expandable=bool(self.relations(model, obj)),
            note=self.object_note(obj),
        )

    def permitted(self, request, queryset):
        """Only the objects the person may act on, as the lists do."""
        model = queryset.model
        perms = get_all_perms_for_model_cached(model)
        if any(request.user.has_perm(p) for p in perms):
            return queryset
        return get_objects_for_user(
            request.user, perms, queryset, use_groups=True, any_perm=True
        )

    def list_nodes(self, request, queryset, more_url=None, more_label=None):
        queryset = self.permitted(request, queryset)
        objects = list(queryset[: LIMIT + 1])
        nodes = [self.object_node(obj) for obj in objects[:LIMIT]]
        if len(objects) > LIMIT and more_url:
            total = queryset.count()
            nodes.append(
                Node(
                    key=self.key("more"),
                    label=str(
                        _("All %(count)d %(things)s")
                        % {"count": total, "things": more_label or ""}
                    ),
                    url=more_url,
                    icon=self.shell.icons["more"],
                    more=True,
                )
            )
        return nodes

    # ------------------------------------------------------------------
    # Children

    def children(self, request, local):
        """The nodes inside the node ``local``; an unknown key has none."""
        try:
            if local == "":
                return [
                    self.section_node(request, n, section)
                    for n, section in enumerate(self.sections())
                ]
            if local.startswith("s"):
                return self.section_children(request, int(local[1:]))
            if local.startswith("o:"):
                obj = self.lookup(local, request)
                return self.object_children(request, obj) if obj else []
            if local.startswith("g:"):
                return self.group_children(request, local)
            if local.startswith("x:"):
                __, name, arg = local.split(":", 2)
                return self.custom_children(request, name, arg)
        except (ValueError, IndexError, LookupError, NoReverseMatch):
            logger.debug("explorer: no children for %r", local, exc_info=True)
        return []

    def section_children(self, request, index):
        section = self.sections()[index]
        if section.model is None:
            return []
        return self.list_nodes(
            request,
            section.model._default_manager.all(),
            more_url=section.url,
            more_label=str(section.model._meta.verbose_name_plural),
        )

    def object_children(self, request, obj):
        model = type(obj)
        rels = self.relations(model, obj)
        nodes = []
        for rel in rels:
            if self.is_flat(model, rel, rels):
                nodes.extend(self.rel_nodes(request, obj, rel))
            else:
                nodes.append(self.group_node(obj, rel))
        return nodes

    def group_node(self, obj, rel, value=None, label=None):
        local = "g:%s:%s:%s" % (_model_label(type(obj)), obj.pk, rel.name)
        if value is not None:
            local += ":%s" % value
        if label is None:
            if isinstance(rel, Folder):
                label = str(rel.label)
            else:
                label = self.rel_label(type(obj), rel)
        icon = self.shell.icon(rel.icon or "folder")
        url = _url(obj)
        if url and not isinstance(rel, Folder):
            url = "%s#%s-tab" % (url, rel.name)
        return Node(
            key=self.key(local), label=label, url=url, icon=icon, expandable=True
        )

    def rel_queryset(self, obj, rel):
        return getattr(obj, rel.name).all()

    def rel_nodes(self, request, obj, rel, value=None):
        if isinstance(rel, Folder):
            return rel.children(self, request, obj)
        queryset = self.rel_queryset(obj, rel)
        if rel.group_by and value is None:
            return self.grouped_nodes(request, obj, rel, queryset)
        if rel.group_by:
            queryset = queryset.filter(**{"%s__pk" % rel.group_by: value})
        url = _url(obj)
        return self.list_nodes(
            request,
            queryset,
            more_url=url and "%s#%s-tab" % (url, rel.name),
            more_label=str(queryset.model._meta.verbose_name_plural),
        )

    def grouped_nodes(self, request, obj, rel, queryset):
        field = queryset.model._meta.get_field(rel.group_by)
        values = (
            field.related_model._default_manager.filter(
                pk__in=queryset.values(rel.group_by)
            )
            if field.is_relation
            else []
        )
        return [
            self.group_node(obj, rel, value=value.pk, label=str(value))
            for value in values
        ]

    def group_children(self, request, local):
        parts = local.split(":")
        label, pk, name = parts[1], parts[2], parts[3]
        value = parts[4] if len(parts) > 4 else None
        obj = self.lookup("o:%s:%s" % (label, pk), request)
        if obj is None:
            return []
        for rel in self.relations(type(obj), obj):
            if rel.name == name:
                return self.rel_nodes(request, obj, rel, value)
        return []

    def custom_children(self, request, name, arg):
        return []

    def lookup(self, local, request=None):
        """
        The object of an ``o:`` key, or ``None``. One the page already holds
        is used as it is, with the related objects it has already fetched.
        """
        known = getattr(request, "_explorer_objects", {})
        if local in known:
            return known[local]
        try:
            __, label, pk = local.split(":", 2)
            model = apps.get_model(label)
        except (ValueError, LookupError):
            return None
        if not _has_admin_urls(model):
            return None
        try:
            return model._default_manager.get(pk=pk)
        except (model.DoesNotExist, ValueError, TypeError):
            return None
        except Exception:  # noqa: BLE001 - a malformed key (a bad UUID)
            return None

    # ------------------------------------------------------------------
    # Where a page is

    def parent(self, obj, known=()):
        """
        The object ``obj`` nests under: one the page already has (``known``,
        which costs nothing), or else one reached through its foreign keys.
        """
        url = _url(obj)
        if not url:
            return None
        best, best_url = None, ""
        for candidate in known:
            candidate_url = _url(candidate)
            if (
                candidate_url
                and url.startswith(candidate_url)
                and url != candidate_url
                and len(candidate_url) > len(best_url)
            ):
                best, best_url = candidate, candidate_url
        if best is not None:
            return best
        for f in type(obj)._meta.concrete_fields:
            if not (f.is_relation and f.many_to_one):
                continue
            if not _has_admin_urls(f.related_model):
                continue
            try:
                candidate = getattr(obj, f.name)
            except Exception:  # noqa: BLE001 - a missing related object
                continue
            if candidate is None:
                continue
            candidate_url = _url(candidate)
            if (
                candidate_url
                and url.startswith(candidate_url)
                and url != candidate_url
                and len(candidate_url) > len(best_url)
            ):
                best, best_url = candidate, candidate_url
        return best

    def known(self, context):
        """The saved objects with admin pages that the page's context holds."""
        found, seen = [], set()
        for value in context.values():
            if not isinstance(value, models.Model) or value.pk is None:
                continue
            if not isinstance(value, AdminUrlMixin) or id(value) in seen:
                continue
            if getattr(value, "_state", None) is not None and value._state.adding:
                continue
            seen.add(id(value))
            found.append(value)
        return found

    def located(self, request, context):
        """The deepest object of the page's context that the page is under."""
        path = request.path
        best, best_url = None, ""
        for value in self.known(context):
            url = _url(value)
            if url and path.startswith(url) and len(url) > len(best_url):
                best, best_url = value, url
        return best

    def trail(self, request, context):
        """
        The keys from the component down to where the page is, each the
        child of the one before. The last is the page's own node, when it
        has one.
        """
        obj = self.located(request, context)
        known = self.known(context)
        chain = []
        while obj is not None and len(chain) < 20:
            chain.insert(0, obj)
            obj = self.parent(obj, known)
        try:
            objects = request.__dict__.setdefault("_explorer_objects", {})
            for each in chain:
                objects[_key(each)] = each
        except AttributeError:
            pass

        sections = self.sections()
        keys = []
        if chain:
            top = chain[0]
            for n, section in enumerate(sections):
                if section.model is not None and isinstance(top, section.model):
                    keys.append(self.key("s%d" % n))
                    break
            else:
                top_url = _url(top) or ""
                n = self._section_for_path(sections, top_url)
                if n is not None:
                    keys.append(self.key("s%d" % n))
            for parent, child in zip([None, *chain], chain):
                if parent is not None:
                    keys.extend(self._steps(parent, child))
                keys.append(self.key(_key(child)))
        else:
            n = self._section_for_path(sections, request.path)
            if n is not None:
                keys.append(self.key("s%d" % n))
        return keys

    def _section_for_path(self, sections, path):
        best, best_len = None, 0
        for n, section in enumerate(sections):
            if path.startswith(section.url) and len(section.url) > best_len:
                best, best_len = n, len(section.url)
        return best

    def _steps(self, parent, child):
        """The folder keys between ``parent`` and its child ``child``."""
        model = type(parent)
        rels = self.relations(model, parent)
        for rel in rels:
            if isinstance(rel, Folder):
                continue
            accessor = getattr(model, rel.name, None)
            related = getattr(getattr(accessor, "rel", None), "related_model", None)
            if related is None or not isinstance(child, related):
                continue
            if self.is_flat(model, rel, rels):
                return []
            local = "g:%s:%s:%s" % (_model_label(model), parent.pk, rel.name)
            steps = [self.key(local)]
            if rel.group_by:
                value = getattr(child, "%s_id" % rel.group_by, None)
                steps.append(self.key("%s:%s" % (local, value)))
            return steps
        return []

    def parent_key(self, request, local):
        """The key of the node ``local`` sits in, for walking back up."""
        if local == "":
            return None
        if local.startswith("s"):
            return self.key("")
        if local.startswith("o:"):
            obj = self.lookup(local)
            if obj is None:
                return self.key("")
            trail = self.trail_of(obj)
            return trail[-2] if len(trail) > 1 else self.key("")
        if local.startswith("g:"):
            parts = local.split(":")
            if len(parts) > 4:
                return self.key(":".join(parts[:4]))
            return self.key("o:%s:%s" % (parts[1], parts[2]))
        return self.key("")

    def trail_of(self, obj):
        """The trail of keys down to ``obj``, as if its page were shown."""

        class _Request:
            path = _url(obj) or ""

        return self.trail(_Request, {"object": obj})

    def label_of(self, request, local):
        """What the node ``local`` is called, for the head of a drill-down."""
        if local == "":
            return str(self.component.verbose_name)
        if local.startswith("s"):
            try:
                return self.sections()[int(local[1:])].label
            except (ValueError, IndexError):
                return ""
        if local.startswith("o:"):
            obj = self.lookup(local)
            return self.object_label(obj) if obj else ""
        if local.startswith("g:"):
            parts = local.split(":")
            obj = self.lookup("o:%s:%s" % (parts[1], parts[2]))
            if obj is None:
                return ""
            for rel in self.relations(type(obj), obj):
                if rel.name == parts[3]:
                    if len(parts) > 4 and rel.group_by:
                        for node in self.grouped_nodes(
                            request, obj, rel, self.rel_queryset(obj, rel)
                        ):
                            if node.key == self.key(local):
                                return node.label
                    if isinstance(rel, Folder):
                        return str(rel.label)
                    return self.rel_label(type(obj), rel)
        return ""

    def url_of(self, request, local):
        if local == "":
            return str(self.component.reverse("index"))
        if local.startswith("s"):
            try:
                return self.sections()[int(local[1:])].url
            except (ValueError, IndexError):
                return None
        if local.startswith("o:"):
            obj = self.lookup(local)
            return _url(obj) if obj else None
        return None


@dataclass
class Tree:
    """The whole explorer for one page: every component, opened down to it."""

    roots: list = field(default_factory=list)
    trail: list = field(default_factory=list)
    here: Node | None = None
    crumbs: list = field(default_factory=list)
    up: Node | None = None
    drill_key: str | None = None
    drill_label: str = ""
    drill_url: str | None = None
    drill_parent: str | None = None
    drill_parent_label: str = ""
    drill_parent_url: str | None = None
    drill_children: list = field(default_factory=list)


def component_for(request, context, components):
    """The component a page belongs to: the context says, or its URL does."""
    component = context.get("component")
    if component is not None:
        return component
    best, best_len = None, 0
    for __, __, url, candidate, __ in components:
        url = str(url)
        if request.path.startswith(url) and len(url) > best_len:
            best, best_len = candidate, len(url)
    return best


def _open(explorer, request, level, trail):
    """Open ``level`` down along ``trail``; the last node found is current."""
    last = None
    for key in trail:
        found = next((node for node in level if node.key == key), None)
        if found is None:
            break
        found.on_trail = True
        last = found
        if found.expandable:
            local = key.split("/", 1)[1]
            found.children = explorer.children(request, local)
            found.open = True
            level = found.children
            if not found.children:
                # An empty folder on the way to the page has nothing to open.
                found.expandable = False
        else:
            break
    if last is not None:
        last.current = True
    return last


def build_tree(request, context, components):
    """
    The explorer for the page: one root per component the person may use,
    the page's own component opened down to where the page is, and the
    drill-down (the phone's view of the same tree) at that place.
    """
    tree = Tree()
    active = component_for(request, context, components)
    flat = context.flatten() if hasattr(context, "flatten") else dict(context)
    for verbose_name, __, url, component, __ in components:
        if not getattr(component, "visible", True):
            continue
        explorer = component.explorer()
        root = Node(
            key=explorer.key(""),
            label=str(verbose_name),
            url=str(url),
            icon=component.shell.component_icon(component),
            expandable=True,
        )
        tree.roots.append(root)
        if active is None or component is active:
            root.children = explorer.children(request, "")
            root.open = True
        if component is not active:
            continue
        root.on_trail = True
        trail = explorer.trail(request, flat)
        tree.trail = trail
        here = _open(explorer, request, root.children, trail) or root
        if here is root:
            root.current = True
        tree.here = here

        # The places above the page, for the location bar and the way up.
        crumbs = [node for node in _walk(root) if node.on_trail]
        if crumbs and (crumbs[-1].url or "").split("#")[0] == request.path:
            crumbs[-1].is_page = True
            crumbs = crumbs[:-1]
        tree.crumbs = crumbs
        # A component's own page only redirects to its first section, so a
        # section has no way up but the menu.
        tree.up = crumbs[-1] if crumbs and crumbs[-1] is not root else None

        # The drill-down shows the folder the page is in: the page's own
        # node when it has anything inside, otherwise the folder holding it.
        if here.expandable and here.children is not None:
            folder = here
            parent_key = (
                trail[-2]
                if len(trail) > 1
                else (root.key if here is not root else None)
            )
        else:
            parent_key = trail[-2] if len(trail) > 1 else root.key
            folder = None
            for node in _walk(root):
                if node.key == parent_key:
                    folder = node
            folder = folder or root
            parent_key = (
                trail[-3]
                if len(trail) > 2
                else (root.key if folder is not root else None)
            )
        tree.drill_key = folder.key
        tree.drill_label = folder.label
        tree.drill_url = folder.url
        tree.drill_children = folder.children or []
        if parent_key is not None:
            parent = next((n for n in _walk(root) if n.key == parent_key), None)
            tree.drill_parent = parent_key
            tree.drill_parent_label = parent.label if parent else ""
            tree.drill_parent_url = parent.url if parent else None
    return tree


def _walk(node):
    yield node
    for child in node.children or ():
        yield from _walk(child)


def drill(request, component, local):
    """The drill-down at the node ``local`` of ``component``."""
    explorer = component.explorer()
    tree = Tree()
    tree.drill_key = explorer.key(local)
    tree.drill_label = explorer.label_of(request, local)
    tree.drill_url = explorer.url_of(request, local)
    tree.drill_children = explorer.children(request, local)
    parent = explorer.parent_key(request, local)
    if parent is not None:
        parent_local = parent.split("/", 1)[1]
        tree.drill_parent = parent
        tree.drill_parent_label = explorer.label_of(request, parent_local)
        tree.drill_parent_url = explorer.url_of(request, parent_local)
    return tree
