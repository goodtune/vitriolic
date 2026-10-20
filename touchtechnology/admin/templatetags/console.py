"""
Template tags of the console admin: icons, the trail, form controls, counts.

``{% load console %}`` in any admin template, a deployment's included.
"""

import copy
import re

from django import forms
from django.db.models import Manager, Model, QuerySet
from django.template import Library
from django.templatetags.static import static
from django.urls import NoReverseMatch
from django.utils.html import format_html

from touchtechnology.admin import console
from touchtechnology.admin.sites import site as default_site
from touchtechnology.admin.templatetags.admin import allowed

register = Library()

ICONS = "touchtechnology/admin/console/icons.svg"

#: Classes that forms outside the admin give their widgets for other themes.
FOREIGN_CLASSES = {"form-control"}

#: Widgets from outside the admin that the console dresses with its own template.
WIDGET_TEMPLATES = {
    "touchtechnology/common/widgets/location_widget.html": (
        "touchtechnology/admin/widgets/location_widget.html"
    ),
}

#: A select with more options than this is chosen from a dialog with search.
PICKER_THRESHOLD = 12

#: A form prefix that marks a form of a formset, whose selects stay in the row.
FORMSET_PREFIX = re.compile(r"(^|-)\d+$")


@register.simple_tag
def icon(name, label=""):
    """
    An icon from the console's sprite. Without a ``label`` it is decoration
    and hidden from assistive technology; with one, the label is its name.
    """
    href = f"{static(ICONS)}#i-{name}"
    if label:
        return format_html(
            '<svg class="i" role="img" aria-label="{}"><use href="{}"></use></svg>',
            label,
            href,
        )
    return format_html(
        '<svg class="i" aria-hidden="true" focusable="false"><use href="{}"></use></svg>',
        href,
    )


@register.simple_tag(takes_context=True)
def admin_trail(context):
    """The pages above this one, outermost first (see ``console.trail``)."""
    request = context.get("request")
    if request is None:
        return []
    # The objects the view already loaded name their own steps of the trail.
    known = {}
    for value in context.flatten().values():
        if isinstance(value, Model) and value.pk is not None:
            for cls in type(value).__mro__:
                if isinstance(cls, type) and issubclass(cls, Model):
                    known.setdefault((cls, str(value.pk)), value)
    return console.trail(request.path, known)


@register.filter
def admin_url(obj, view):
    """
    The admin URL ``view`` of ``obj`` (``edit``, ``delete``, ``perms`` ...), or
    an empty string when the object has no such page.
    """
    try:
        return str(obj.urls[view])
    except (AttributeError, KeyError, NoReverseMatch, TypeError, ValueError):
        return ""


@register.filter
def site_url(obj):
    """Where ``obj`` is on the public site, or an empty string."""
    try:
        return obj.get_absolute_url() or ""
    except Exception:  # noqa: BLE001 - a public route that is not mounted
        return ""


@register.filter
def count_of(manager):
    """How many objects a related manager or queryset holds."""
    if isinstance(manager, (Manager, QuerySet)):
        try:
            return manager.count()
        except Exception:  # noqa: BLE001 - a manager that cannot be counted
            return ""
    return ""


@register.filter
def number_key(obj):
    """The primary key of ``obj`` when it is a number worth showing, else ''."""
    pk = getattr(obj, "pk", None)
    return pk if isinstance(pk, int) else ""


def _picker(bf):
    """Whether the select of ``bf`` is chosen from a dialog, and how."""
    widget = bf.field.widget
    if not isinstance(widget, forms.Select) or isinstance(
        widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)
    ):
        return None
    if isinstance(widget, forms.SelectMultiple):
        return "multiple"
    if bf.form.prefix and FORMSET_PREFIX.search(bf.form.prefix):
        return None
    choices = getattr(bf.field, "choices", None)
    if choices is None:
        choices = getattr(widget, "choices", ())
    try:
        many = len(choices) > PICKER_THRESHOLD
    except TypeError:
        many = len(list(choices)) > PICKER_THRESHOLD
    return "single" if many else None


def control_attrs(bf, extra=None):
    """
    The attributes the console gives the control of ``bf``: no class another
    theme asked for, no placeholder that only repeats the label, the help and
    error texts it is described by, and how a long select is chosen.
    """
    widget = bf.field.widget
    attrs = {}
    classes = [
        c for c in (widget.attrs.get("class") or "").split() if c not in FOREIGN_CLASSES
    ]
    attrs["class"] = " ".join(classes) or False
    placeholder = widget.attrs.get("placeholder")
    if placeholder is not None and str(placeholder) == str(bf.label):
        attrs["placeholder"] = False
    described = []
    if bf.help_text:
        described.append(f"{bf.auto_id}_helptext")
    if bf.errors:
        described.append(f"{bf.auto_id}_error")
        attrs["aria-invalid"] = "true"
    if described and bf.auto_id:
        attrs["aria-describedby"] = " ".join(described)
    picker = _picker(bf)
    if picker:
        attrs["data-picker"] = picker
    if extra:
        attrs.update(extra)
    return attrs


@register.simple_tag
def control(bf, **extra):
    """
    Render the widget of the bound field ``bf`` for the console. A plain date
    field is a native date input, which a phone shows as its date picker.
    """
    if not hasattr(bf, "as_widget"):
        return bf
    widget = bf.field.widget
    attrs = control_attrs(bf, {k.replace("_", "-"): v for k, v in extra.items()})
    if type(widget) is forms.DateInput:
        widget = copy.copy(widget)
        widget.input_type = "date"
        widget.format = "%Y-%m-%d"
        return bf.as_widget(widget=widget, attrs=attrs)
    if getattr(widget, "template_name", None) in WIDGET_TEMPLATES:
        widget = copy.copy(widget)
        widget.template_name = WIDGET_TEMPLATES[widget.template_name]
        return bf.as_widget(widget=widget, attrs=attrs)
    if type(widget) is forms.TimeInput:
        widget = copy.copy(widget)
        widget.input_type = "time"
        widget.format = "%H:%M"
        return bf.as_widget(widget=widget, attrs=attrs)
    return bf.as_widget(attrs=attrs)


@register.filter
def is_checkbox(bf):
    return isinstance(
        getattr(bf, "field", None) and bf.field.widget, forms.CheckboxInput
    )


@register.filter
def is_group(bf):
    """A widget of several controls, labelled as a group rather than by <label>."""
    widget = getattr(getattr(bf, "field", None), "widget", None)
    return isinstance(
        widget, (forms.RadioSelect, forms.CheckboxSelectMultiple, forms.MultiWidget)
    )


@register.filter
def is_wide(bf):
    """A control that takes the width of the form (rich text, long text)."""
    widget = getattr(getattr(bf, "field", None), "widget", None)
    return isinstance(widget, forms.Textarea)


#: The icon of a component in the menu, by its application name.
COMPONENT_ICONS = {
    "competition": "trophy",
    "content": "sitemap",
    "news": "news",
    "auth": "users",
    "enrolment": "school",
    "settings": "settings",
}


@register.simple_tag(takes_context=True)
def admin_nav(context):
    """
    The menu: one group per component the person may use, each with the
    places it offers. The group and the place this page belongs to are marked
    current (the longest address that this page's address begins with).
    """
    request = context.get("request")
    if request is None or not request.user.is_authenticated:
        return []
    admin = context.get("admin") or default_site
    path = request.path
    groups = []
    best = ("", None, None)
    for verbose_name, app_name, url, component, schemas in allowed(
        admin.get_components(), request
    ):
        if not component.visible:
            continue
        items = []
        for entry in component.dropdowns() or ((verbose_name, url),):
            item = {"label": entry[0], "url": str(entry[1]), "current": ""}
            items.append(item)
        group = {
            "key": app_name,
            "label": verbose_name,
            "icon": COMPONENT_ICONS.get(app_name, "list"),
            "items": items,
            "current": False,
        }
        groups.append(group)
        prefixes = [(str(url), group, None)] + [(i["url"], group, i) for i in items]
        for prefix, g, item in prefixes:
            if path.startswith(prefix) and len(prefix) > len(best[0]):
                best = (prefix, g, item)
    __, group, item = best
    if group is not None:
        group["current"] = True
    if item is not None:
        item["current"] = "page" if item["url"] == path else "true"
    return groups


@register.simple_tag(takes_context=True)
def page_query(context, number):
    """
    The query string of page ``number`` of this list: the page first, then
    whatever else the address asked for (a search, a filter).
    """
    request = context.get("request")
    query = request.GET.copy() if request is not None else None
    rest = ""
    if query is not None:
        query.pop("page", None)
        query.pop("_htmx_tab", None)
        rest = query.urlencode()
    return "?page={}{}{}".format(number, "&" if rest else "", rest)


@register.filter
def page_number(page):
    """The number of the page on show: a ``Page`` or a plain number."""
    return getattr(page, "number", page)


@register.simple_tag
def dom_id(*parts):
    """An id for an element, made of ``parts`` (any text, a primary key...)."""
    return "-".join(re.sub(r"[^A-Za-z0-9_-]+", "-", str(p)).strip("-") for p in parts)


@register.filter
def sheetable(formset):
    """
    Whether the forms of ``formset`` fit as rows of a table: none of their
    fields is a long text or a widget of several controls.
    """
    try:
        form = formset.empty_form
    except Exception:  # noqa: BLE001 - a formset with no empty form
        return False
    for bf in form.visible_fields():
        widget = bf.field.widget
        if isinstance(
            widget,
            (
                forms.Textarea,
                forms.MultiWidget,
                forms.CheckboxSelectMultiple,
                forms.SelectMultiple,
                forms.RadioSelect,
            ),
        ):
            return False
    return True


@register.filter
def total_of(paginator, object_list):
    """How many objects a list holds in all: its paginator's count, or the list's."""
    if paginator:
        return paginator.count
    try:
        return len(object_list)
    except TypeError:
        return 0
