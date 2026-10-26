"""
[Developer API] Template tags and filters of the admin's interface.

``{% load admin_workbook %}`` gives a Workbook template:

- ``{% icon "name" %}``: an icon from the admin's sprite, hidden from
  assistive technology unless given a label (``{% icon "trash-2" "Delete" %}``).
- ``{{ bound_field|control }}``: a form field's control, drawn the admin's way.
- ``{{ form.media|admin_media }}``: a form's assets, served by the admin.
- ``{% trail %}``: the pages above this one, as links.
- ``{% admin_nav %}``: the rail of components and their sections.
- ``{{ user|initials }}``: one or two letters for an avatar.
"""

from django import template
from django.http import QueryDict
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from touchtechnology.admin.explorer import build_tree
from touchtechnology.admin.helpers import admin_media as _admin_media
from touchtechnology.admin.helpers import initials as _initials
from touchtechnology.admin.templatetags.admin import allowed
from touchtechnology.admin.trail import build_trail
from touchtechnology.admin.widgets import kind_of, render_field

register = template.Library()

SPRITE = "touchtechnology/admin/workbook/icons.svg"


@register.simple_tag
def icon(name, label=None, size=None):
    href = f"{static(SPRITE)}#{name}"
    style = format_html(' style="--icon-size:{}"', size) if size else ""
    if label:
        return format_html(
            '<svg class="wb-icon" role="img" aria-label="{}"{}>'
            '<use href="{}"></use></svg>',
            label,
            style,
            href,
        )
    return format_html(
        '<svg class="wb-icon" aria-hidden="true" focusable="false"{}>'
        '<use href="{}"></use></svg>',
        style,
        href,
    )


@register.filter
def control(bound_field):
    """The control of ``bound_field`` with the admin's classes and types."""
    return render_field(bound_field)


@register.filter(is_safe=True)
def label_text(caption):
    """A field's caption without the colon Django puts after the label."""
    caption = str(caption)
    for closing in ("</label>", "</span>", ""):
        if caption.endswith(":" + closing):
            return mark_safe(
                caption[: -len(closing) - 1] + closing if closing else caption[:-1]
            )
    return mark_safe(caption)


@register.simple_tag(takes_context=True)
def page_query(context, number):
    """
    The query string for page ``number`` of a list: the page's own query
    without its page, and the page last (``?page=2`` when there is no other).
    """
    request = context.get("request")
    query = request.GET.copy() if request is not None else QueryDict(mutable=True)
    query.pop("page", None)
    rest = query.urlencode()
    return f"?{rest}&page={number}" if rest else f"?page={number}"


@register.filter
def field_kind(bound_field):
    return kind_of(bound_field.field.widget)


@register.filter
def admin_media(media):
    return _admin_media(media)


@register.inclusion_tag(
    "touchtechnology/admin/workbook/_trail.html", takes_context=True
)
def trail(context):
    request = context.get("request")
    admin = context.get("admin")
    site_name = getattr(admin, "name", "admin")
    return {"crumbs": build_trail(request, site_name, context.flatten())}


@register.filter
def resolved(url):
    """
    ``url`` as a string, or "" when it is a lazy reverse that has no match
    (a component with flat URL namespaces has no nested add page).
    """
    try:
        return str(url) if url else ""
    except NoReverseMatch:
        return ""


@register.filter
def tab_count(manager):
    """How many objects a tab lists: a count query, or the length of a list."""
    try:
        return manager.count()
    except TypeError:
        return len(manager)
    except AttributeError:
        try:
            return len(manager)
        except TypeError:
            return ""


def default_site():
    """The admin site pages belong to when a view did not say."""
    from touchtechnology.admin.sites import site

    return site


@register.filter
def is_saved(instance):
    """Whether ``instance`` is in the database (an add page's is not yet)."""
    state = getattr(instance, "_state", None)
    return state is not None and not state.adding and instance.pk is not None


@register.filter
def initials(user):
    """Up to two letters for ``user``: their initials, or their user name's first."""
    return _initials(user, single=2)


@register.simple_tag(takes_context=True)
def admin_tree(context):
    """
    The explorer for the page (see ``touchtechnology.admin.explorer``), worked
    out once per request: the rail draws it, and a page's sections are read
    from it.
    """
    request = context.get("request")
    admin = context.get("admin") or default_site()
    if request is None or admin is None:
        return None
    tree = getattr(request, "_admin_explorer", None)
    if tree is None:
        components = allowed(admin.get_components(), request)
        tree = request._admin_explorer = build_tree(request, context, components)
    return tree


@register.inclusion_tag("touchtechnology/admin/workbook/_nav.html", takes_context=True)
def admin_nav(context, placement="rail"):
    """
    The components the person may use, each a folder of the tree (see
    ``touchtechnology.admin.explorer``). The page's own component is opened
    down to where the page is; the others open when asked. On a phone the
    same tree is a drill-down at the folder the page is in.
    """
    request = context.get("request")
    admin = context.get("admin") or default_site()
    path = request.path if request is not None else ""
    entries = []
    tree = None
    if admin is not None and request is not None:
        components = allowed(admin.get_components(), request)
        tree = admin_tree(context)
        roots = {node.key: node for node in tree.roots}
        for verbose_name, __, url, component, __ in components:
            if not component.visible:
                continue
            root = roots.get(component.explorer().key(""))
            entries.append(
                {
                    "label": str(verbose_name),
                    "url": str(url),
                    "active": bool(root and root.on_trail),
                    "root": root,
                    "name": component.name,
                    "icon": component.shell.component_icon(component),
                }
            )
    try:
        home = reverse(f"{getattr(admin, 'name', 'admin')}:index")
    except NoReverseMatch:
        home = "/"
    return {
        "entries": entries,
        "tree": tree,
        "home": home,
        "at_home": path == home,
        "placement": placement,
        "request": request,
    }


@register.simple_tag(takes_context=True)
def admin_tasks(context):
    """
    The jobs the home page offers: each component the person may use names
    its own (``AdminComponentMixin.tasks``), in the order of the menu.
    """
    request = context.get("request")
    admin = context.get("admin") or default_site()
    if admin is None or request is None:
        return []
    tasks = []
    for __, __, __, component, __ in allowed(admin.get_components(), request):
        if not component.visible:
            continue
        for task in component.tasks(request) or ():
            task = dict(task)
            if not task.get("icon"):
                task["icon"] = component.shell.component_icon(component)
            tasks.append(task)
    return sorted(tasks, key=lambda task: task.get("priority", 50))


@register.simple_tag
def fields_in(form, names):
    """The bound fields of ``form`` named in ``names`` (space separated), in that order."""
    return [form[name] for name in names.split() if name in form.fields]


@register.simple_tag
def fields_besides(form, names):
    """The bound fields of ``form`` not named in ``names`` (space separated)."""
    named = set(names.split())
    return [field for field in form if field.name not in named]
