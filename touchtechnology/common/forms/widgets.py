import logging

from django import forms
from django.forms.widgets import DateInput, MultiWidget, Select, TimeInput
from django.utils import timezone
from timezone_field.backends import get_tz_backend
from timezone_field.choices import with_gmt_offset

logger = logging.getLogger(__name__)


class HTMLWidget(forms.Textarea):
    def __init__(self, attrs=None):
        defaults = {"class": "html_widget"}
        if attrs:
            defaults.update(attrs)
        super().__init__(attrs=defaults)

    class Media:
        css = {
            "all": (
                "touchtechnology/common/css/jodit.min.css",
            ),
        }
        js = (
            "touchtechnology/common/js/jodit.min.js",
            "touchtechnology/common/js/html-editor.js",
        )


class GoogleMapsWidget(MultiWidget):
    def __init__(self, height, width, zoom, attrs=None):
        if attrs is None:
            attrs = {}
        self.attrs = attrs
        self.height = height
        self.width = width
        self.zoom = zoom
        widgets = (
            forms.TextInput(attrs=dict(placeholder="Latitude", **attrs)),
            forms.TextInput(attrs=dict(placeholder="Longitude", **attrs)),
            forms.TextInput(attrs=dict(placeholder="Zoom", **attrs)),
        )
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            return value.split(",")
        return ("", "", "")


class SelectDateTimeWidget(MultiWidget):
    def __init__(
        self,
        attrs=None,
        date_format=None,
        time_format=None,
        date_attrs=None,
        time_attrs=None,
        use_pytz=False,
    ):
        tz_backend = get_tz_backend(use_pytz=use_pytz)
        tz_choices = [("", "---")] + with_gmt_offset(
            tz_backend.base_tzstrs, use_pytz=use_pytz
        )
        widgets = (
            DateInput(
                attrs=attrs if date_attrs is None else date_attrs,
                format=date_format,
            ),
            TimeInput(
                attrs=attrs if time_attrs is None else time_attrs,
                format=time_format,
            ),
            Select(attrs=attrs, choices=tz_choices),
        )
        super().__init__(widgets)

    def decompress(self, value):
        if value:
            value = value.astimezone(timezone.get_current_timezone())
            return [value.date(), value.time(), value.tzinfo]
        return [None, None, None]


class SelectDateTimeHiddenWidget(SelectDateTimeWidget):
    def __init__(self, attrs=None):
        widgets = (
            forms.HiddenInput(),
            forms.HiddenInput(),
            forms.HiddenInput(),
        )
        super().__init__(widgets, attrs)
