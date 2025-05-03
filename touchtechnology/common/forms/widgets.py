import logging
from importlib import metadata

from django import forms
from django.forms.widgets import DateInput, MultiWidget, Select, TimeInput
from django.utils import timezone
from froala_editor.widgets import FroalaEditor
from timezone_field.backends import get_tz_backend
from timezone_field.choices import with_gmt_offset

logger = logging.getLogger(__name__)


class HTMLWidget(FroalaEditor):
    def trigger_froala(self, *args, **kwargs):
        """
        We don't want to do inline scripts, we'll handle the loading once from
        froala.js, so return an empty string to overload the base FroalaEditor
        implementation.

        Note: required for django-froala-editor<3 AFAICT
        """
        version = metadata.version("django-froala-editor")
        if int(version.split(".")[0]) < 3:
            return ""
        return super().trigger_froala(*args, **kwargs)

    class Media:
        css = {
            "all": (
                "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.3.0/"
                "codemirror.min.css",
                "touchtechnology/common/css/froala_themes/dark.min.css",
                "touchtechnology/common/css/froala_themes/gray.min.css",
                "touchtechnology/common/css/froala_themes/red.min.css",
                "touchtechnology/common/css/froala_themes/royal.min.css",
            ),
        }
        js = (
            "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.3.0/codemirror.min.js",
            "touchtechnology/common/js/froala.js",
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
