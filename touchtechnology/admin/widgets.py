"""
The admin's presentation of form widgets.

Forms are shared with the public site and with deployments, so the admin does
not change them. Instead it renders each bound field through ``admin_widget``,
which gives the widget the admin's own classes and input types, and swaps the
few widgets whose markup or assets the admin needs to own.
"""

import copy

from django.forms import widgets as django_widgets

from touchtechnology.common.forms.widgets import LocationWidget

#: Classes a form may still set on its widgets for the old theme. The admin
#: does not use them, so they are dropped when a field is rendered.
LEGACY_CLASSES = frozenset(
    {"form-control", "input-sm", "input-lg", "text-center", "btn", "btn-default"}
)

#: A select with more choices than this opens a dialog with a search box.
PICKER_THRESHOLD = 10

#: Remote assets a widget may declare, and the copy the admin serves itself.
SELF_HOSTED = {
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css": (
        "touchtechnology/admin/workbook/vendor/leaflet/leaflet.css"
    ),
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js": (
        "touchtechnology/admin/workbook/vendor/leaflet/leaflet.js"
    ),
}


class AdminLocationWidget(LocationWidget):
    """The location widget with the admin's markup and a self-hosted map."""

    template_name = "touchtechnology/admin/widgets/location_widget.html"

    class Media:
        css = {"all": ("touchtechnology/admin/workbook/vendor/leaflet/leaflet.css",)}
        js = (
            "touchtechnology/admin/workbook/vendor/leaflet/leaflet.js",
            "touchtechnology/common/js/location-widget.js",
        )


def kind_of(widget):
    """A short name for the sort of control a widget draws, for styling."""
    if isinstance(widget, django_widgets.CheckboxSelectMultiple):
        return "checks"
    if isinstance(widget, django_widgets.RadioSelect):
        return "radios"
    if isinstance(widget, django_widgets.CheckboxInput):
        return "check"
    if isinstance(widget, django_widgets.Select):
        return "select"
    if isinstance(widget, django_widgets.Textarea):
        return "textarea"
    if isinstance(widget, django_widgets.ClearableFileInput):
        return "file"
    if isinstance(widget, django_widgets.FileInput):
        return "file"
    if isinstance(widget, django_widgets.MultiWidget):
        return "multi"
    return "input"


def choice_count(widget):
    try:
        return len(widget.choices)
    except TypeError:
        return 0


def admin_widget(widget):
    """
    The widget to draw for ``widget``: a copy with the admin's input types,
    or the admin's own variant of a widget whose markup it owns. The widget
    the form holds is never changed.
    """
    kind = type(widget)
    if kind is LocationWidget:
        swapped = copy.copy(widget)
        swapped.__class__ = AdminLocationWidget
        return swapped
    if kind is django_widgets.DateInput:
        swapped = copy.copy(widget)
        swapped.input_type = "date"
        swapped.format = "%Y-%m-%d"
        return swapped
    if kind is django_widgets.TimeInput:
        swapped = copy.copy(widget)
        swapped.input_type = "time"
        swapped.format = "%H:%M"
        return swapped
    if kind is django_widgets.DateTimeInput:
        swapped = copy.copy(widget)
        swapped.input_type = "datetime-local"
        swapped.format = "%Y-%m-%dT%H:%M"
        return swapped
    return widget


def admin_attrs(bound_field, widget):
    """The attributes the admin gives a field's control when it draws it."""
    kept = [
        name
        for name in str(widget.attrs.get("class", "")).split()
        if name not in LEGACY_CLASSES
    ]
    kind = kind_of(widget)
    kept.insert(0, "wb-%s" % kind)
    attrs = {"class": " ".join(kept)}

    # A placeholder that repeats the label says nothing, and hides once the
    # person types; the label is always on show.
    placeholder = widget.attrs.get("placeholder")
    if placeholder is not None and str(placeholder) == str(bound_field.label):
        attrs["placeholder"] = False

    described = []
    if bound_field.help_text:
        described.append("%s_help" % bound_field.auto_id)
    if bound_field.errors:
        described.append("%s_error" % bound_field.auto_id)
        attrs["aria-invalid"] = "true"
    if described and kind not in ("radios", "checks", "multi"):
        attrs["aria-describedby"] = " ".join(described)

    if kind == "select" and (
        getattr(widget, "allow_multiple_selected", False)
        or choice_count(widget) > PICKER_THRESHOLD
    ):
        attrs["data-picker"] = "dialog"
    if kind == "checks" and choice_count(widget) > PICKER_THRESHOLD:
        attrs["data-picker"] = "dialog"
    return attrs


def render_field(bound_field):
    widget = admin_widget(bound_field.field.widget)
    return bound_field.as_widget(widget=widget, attrs=admin_attrs(bound_field, widget))


def admin_media(media):
    """``media`` with the remote assets it names swapped for the admin's copies."""
    if not isinstance(media, django_widgets.Media):
        return media or ""
    js = [SELF_HOSTED.get(str(path), path) for path in media._js]
    css = {
        medium: [SELF_HOSTED.get(str(path), path) for path in paths]
        for medium, paths in media._css.items()
    }
    return django_widgets.Media(css=css, js=js)
