"""
[Developer API] Template tags and filters of the Explorer shell.

``{% load admin_explorer %}`` gives an Explorer template:

- ``{% icon "name" %}``: an icon from the shell's sprite, hidden from assistive
  technology unless given a label.
- ``{% explorer_tree %}``: the tree of the admin for the rail.
- ``{{ bound_field|widget }}``: a form field's control, drawn the shell's way.
- ``{{ form.media|admin_media }}``: a form's assets, served by the admin.
- ``{{ user|initials }}``: one or two letters for an avatar.
"""

from urllib.parse import parse_qsl, urlencode

from django.forms.boundfield import BoundField
from django.template import Library
from django.templatetags.static import static
from django.urls import NoReverseMatch
from django.utils.html import format_html

from touchtechnology.admin.explorer import build_tree
from touchtechnology.admin.helpers import admin_media as _admin_media
from touchtechnology.admin.helpers import initials as _initials
from touchtechnology.admin.templatetags.admin import allowed

register = Library()

#: Other names for the admin's icons: model names and the Font Awesome names
#: components gave their menu entries before the admin drew its own.
ICON_ALIASES = {
    # Font Awesome names used by ``dropdowns()``
    "trophy": "competition",
    "shield": "club",
    "wrench": "drawformat",
    "book": "report",
    "calendar": "schoolyear",
    "sort-numeric-asc": "grade",
    "graduation-cap": "student",
    "users": "group",
    "pencil-square-o": "chunk",
    "reply": "redirect",
    "puzzle-piece": "puzzle",
    "newspaper-o": "article",
    "tag": "category",
    "dashboard": "dashboard",
    # model names
    "undecidedteam": "team",
    "teamassociation": "person",
    "clubassociation": "person",
    "clubrole": "club",
    "teamrole": "team",
    "seasonmatchtime": "clock",
    "seasonexclusiondate": "ban",
    "divisionexclusiondate": "ban",
    "seasonreferee": "referee",
    "livestreamevent": "video",
    "livestreamkey": "key",
    "matchscoresheet": "image",
    "attendancerecord": "attendance",
    "sitemapnode": "page",
    "placeholder": "puzzle",
    "redirect": "redirect",
    "chunk": "chunk",
    "simplescorematchstatistic": "chart",
    "ladderentry": "ladder",
    "more": "more",
}

#: The icons the sprite has; anything else is drawn as a document.
ICONS = {
    "component", "folder", "folder-open", "item", "chevron-right",
    "chevron-left", "chevron-down", "up", "arrow-up", "arrow-down",
    "competition", "season", "division", "stage", "stagegroup", "team", "club",
    "person", "venue", "ground", "match", "clock", "ban", "referee", "video",
    "key", "drawformat", "report", "article", "category", "translation",
    "page", "sitemap", "image", "puzzle", "redirect", "chunk", "settings",
    "logout", "plus", "plus-many", "trash", "edit", "eye", "lock", "search",
    "menu", "tree", "x", "check", "more", "external", "upload", "download",
    "print", "schoolyear", "grade", "classgroup", "teacher", "student",
    "enrolment", "attendance", "assessment", "reportcard", "user", "group",
    "home", "undo", "play", "results", "allocate", "umbrella", "alert", "info",
    "link", "copy", "merge", "transfer", "refresh", "chart", "ladder", "json",
    "dashboard",
}  # fmt: skip


def icon_name(name):
    name = ICON_ALIASES.get(name, name)
    return name if name in ICONS else "item"


@register.simple_tag
def icon(name, label=""):
    """
    An icon of the admin's sprite. Without a ``label`` it is decoration and
    hidden from assistive technology; with one it is named by it.
    """
    href = "%s#%s" % (
        static("touchtechnology/admin/explorer/img/icons.svg"),
        icon_name(name),
    )
    if label:
        return format_html(
            '<svg class="icon" role="img" aria-label="{}"><use href="{}"></use></svg>',
            label,
            href,
        )
    return format_html(
        '<svg class="icon" aria-hidden="true" focusable="false"><use href="{}"></use></svg>',
        href,
    )


@register.simple_tag(takes_context=True)
def explorer_tree(context):
    """
    The explorer for the page (see ``touchtechnology.admin.explorer``),
    worked out once per request.
    """
    request = context.get("request")
    if request is None or not getattr(request, "user", None):
        return None
    if not request.user.is_authenticated or not request.user.is_staff:
        return None
    tree = getattr(request, "_admin_explorer", None)
    if tree is None:
        admin_site = context.get("admin")
        if not hasattr(admin_site, "get_components"):
            # Imported here: the admin site imports this module.
            from touchtechnology.admin.sites import site as admin_site
        components = allowed(admin_site.get_components(), request)
        tree = build_tree(request, context, components)
        request._admin_explorer = tree
    return tree


@register.filter
def widget(bound_field, extra_class=""):
    """
    Render a form field's widget for the admin: without the public site's
    ``form-control`` class that the shared form mixin gives every widget.
    """
    if not isinstance(bound_field, BoundField):
        return bound_field
    classes = [
        c
        for c in (bound_field.field.widget.attrs.get("class") or "").split()
        if c != "form-control"
    ]
    if extra_class:
        classes.append(extra_class)
    attrs = {"class": " ".join(classes) if classes else False}
    # The shared form mixin repeats each label as a placeholder; beside a
    # visible label that is only noise.
    placeholder = bound_field.field.widget.attrs.get("placeholder")
    if placeholder is not None and str(placeholder) == str(bound_field.label):
        attrs["placeholder"] = False
    if bound_field.errors:
        attrs["aria-invalid"] = "true"
        described = ["%s-errors" % bound_field.auto_id]
        if bound_field.help_text:
            described.append("%s_helptext" % bound_field.auto_id)
        attrs["aria-describedby"] = " ".join(described)
    return bound_field.as_widget(attrs=attrs)


@register.filter
def admin_media(media):
    """
    Form media as the admin loads it: what a widget would fetch from a CDN is
    served from the admin's own static files.
    """
    return _admin_media(media)


@register.filter
def initials(user):
    """One or two letters for a person with no picture."""
    return _initials(user)


@register.filter
def model_icon(obj):
    """The icon name of an object's, a queryset's or a manager's model."""
    model = getattr(obj, "model", None) or type(obj)
    meta = getattr(model, "_meta", None)
    return icon_name(meta.model_name) if meta else "item"


@register.filter
def admin_url(obj, name):
    """
    The admin URL of ``obj`` called ``name`` (``edit``, ``delete``...), or
    ``None`` when the object has no such page.
    """
    urls = getattr(obj, "urls", None)
    if not urls or name not in urls:
        return None
    try:
        return str(urls[name])
    except NoReverseMatch:
        return None


@register.inclusion_tag(
    "touchtechnology/admin/explorer/_pagination.html", takes_context=True
)
def admin_pagination(context):
    """The links to the other pages of a list, keeping its other parameters."""
    query = [
        (key, value)
        for key, value in parse_qsl(context.get("QUERY_STRING") or "", True)
        if key != "page"
    ]
    context.update({"QUERY_STRING": urlencode(query, True)})
    return context


@register.filter
def dates_of(queryset, field="date"):
    """The distinct days of a date field of ``queryset``, in order."""
    try:
        return list(queryset.dates(field, "day"))
    except (AttributeError, TypeError, ValueError):
        return []


@register.simple_tag
def adjacent(sequence, value):
    """The items either side of ``value`` in ``sequence``, as ``previous`` and ``next``."""
    items = list(sequence or ())
    try:
        index = items.index(value)
    except ValueError:
        return {"previous": None, "next": None}
    return {
        "previous": items[index - 1] if index > 0 else None,
        "next": items[index + 1] if index + 1 < len(items) else None,
    }


@register.filter
def saved(obj):
    """
    Whether ``obj`` is in the database: a primary key is not enough, as a
    UUID key is given to an object before it is saved.
    """
    state = getattr(obj, "_state", None)
    if state is None:
        return bool(getattr(obj, "pk", None))
    return obj.pk is not None and not state.adding


@register.filter
def plural_label(queryset):
    """
    The plural name of a queryset's model for a label, with the
    ``entry``/``entrys`` slip of the automatic plural mended.
    """
    model = getattr(queryset, "model", None)
    if model is None:
        return ""
    name = str(model._meta.verbose_name_plural)
    if name.endswith("ys") and len(name) > 2 and name[-3] not in "aeiou":
        name = name[:-2] + "ies"
    return name[:1].upper() + name[1:]
