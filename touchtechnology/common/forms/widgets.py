from __future__ import unicode_literals

import logging

from django import forms
from django.conf import settings
from django.forms import widgets
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from froala_editor.widgets import FroalaEditor

from touchtechnology.common.forms.tz import (
    DAY_CHOICES,
    HOUR_CHOICES,
    MINUTE_CHOICES,
    MONTH_CHOICES,
    TIMEZONE_CHOICES,
)

try:
    from importlib import metadata
except ImportError:  # Python 3.6
    import importlib_metadata as metadata

logger = logging.getLogger(__name__)


class MultiWidget(widgets.MultiWidget):
    def build_attrs(self, *args, **kwargs):
        """
        In the underlying render process for the widget, build_attrs will be
        used to determine the ``final_attrs`` to be associated to each widget.

        Unfortunately in Django 1.10 it seems that "required" is being added
        and this is producing different rendered output than that of earlier
        releases.

        This method is used to restore the pre-1.10 behaviour so our tests can
        continue passing across versions 1.8-1.10.
        """
        import django

        attrs = super(MultiWidget, self).build_attrs(*args, **kwargs)
        if django.VERSION >= (1, 10):
            attrs.pop("required", None)
        return attrs


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
            "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.3.0/"
            "codemirror.min.js",
            "touchtechnology/common/js/froala.js",
        )


class GoogleMapsWidget(MultiWidget):
    def __init__(self, height, width, zoom, attrs=None):
        self.attrs = attrs or {}
        self.height = height
        self.width = width
        self.zoom = zoom
        widgets = (
            forms.HiddenInput(attrs=attrs),
            forms.HiddenInput(attrs=attrs),
            forms.HiddenInput(attrs=attrs),
        )
        super(GoogleMapsWidget, self).__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            return value.split(",")
        return ("", "", "")

    class Media:
        css = {"all": ("touchtechnology/common/css/location_widget.css",)}
        js = (
            "//maps.googleapis.com/maps/api/js?v=3",
            "touchtechnology/common/js/location_widget.js",
        )


class BootstrapGoogleMapsWidget(GoogleMapsWidget):
    def render(self, *args, **kwargs):
        base = super(BootstrapGoogleMapsWidget, self).render(*args, **kwargs)
        return """
            <div class="form-group">
                <label class="control-label col-sm-3">%s</label>
                <div class="col-sm-7">%s</div>
            </div>
        """ % (
            _("Location"),
            base,
        )


class SelectDateWidget(MultiWidget):
    def __init__(self, attrs=None):
        widgets = (
            forms.Select(choices=DAY_CHOICES, attrs=attrs),
            forms.Select(choices=MONTH_CHOICES, attrs=attrs),
            forms.TextInput(attrs=attrs),
        )
        super(SelectDateWidget, self).__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            return (value.day, value.month, value.year)
        return (None, None, None)

    def format_output(self, rendered_widgets):
        return " ".join(rendered_widgets)


class SelectDateHiddenWidget(SelectDateWidget):
    def __init__(self, attrs=None):
        widgets = (
            forms.HiddenInput(attrs=attrs),
            forms.HiddenInput(attrs=attrs),
            forms.HiddenInput(attrs=attrs),
        )
        super(SelectDateWidget, self).__init__(widgets, attrs)


class SelectTimeWidget(MultiWidget):
    def __init__(self, attrs=None):
        widgets = (
            forms.Select(choices=HOUR_CHOICES, attrs=attrs),
            forms.Select(choices=MINUTE_CHOICES, attrs=attrs),
        )
        super(SelectTimeWidget, self).__init__(widgets, attrs)

    def decompress(self, value):
        if value is not None:
            return (value.hour, value.minute)
        return (None, None)

    def format_output(self, rendered_widgets):
        return " ".join(rendered_widgets)


class SelectTimeHiddenWidget(SelectTimeWidget):
    def __init__(self, attrs=None):
        widgets = (
            forms.HiddenInput(attrs=attrs),
            forms.HiddenInput(attrs=attrs),
        )
        super(SelectTimeWidget, self).__init__(widgets, attrs)


class SelectDateTimeWidget(MultiWidget):
    def __init__(self, attrs=None):
        widgets = (
            forms.Select(choices=DAY_CHOICES, attrs=attrs),
            forms.Select(choices=MONTH_CHOICES, attrs=attrs),
            forms.TextInput(attrs=attrs),
            forms.Select(choices=HOUR_CHOICES, attrs=attrs),
            forms.Select(choices=MINUTE_CHOICES, attrs=attrs),
        )
        if settings.USE_TZ:
            widgets += (forms.Select(choices=TIMEZONE_CHOICES, attrs=attrs),)
        super(SelectDateTimeWidget, self).__init__(widgets, attrs)

    def decompress(self, value):
        if settings.USE_TZ:
            tzinfo = timezone.get_current_timezone()
            tzname = timezone.get_current_timezone_name()
            logger.debug("USE_TZ is True, timezone is %s (%s)", tzinfo, tzname)

            if value:
                logger.debug("Value is set (%s)", value)
                if timezone.is_naive(value):
                    value = timezone.make_aware(value, timezone.get_default_timezone())
                    logger.debug("Naive value, set default timezone (%s)", value)
                value = value.astimezone(tzinfo)
                logger.debug(
                    "Ensure timezone is correctly set to %s (%s)", tzname, value
                )
                values = (
                    value.day,
                    value.month,
                    value.year,
                    value.hour,
                    value.minute,
                    tzname,
                )
            else:
                values = (None, None, None, None, None, None)

        elif value:
            values = (value.day, value.month, value.year, value.hour, value.minute)

        else:
            values = (None, None, None, None, None)

        return values

    def format_output(self, rendered_widgets):
        date_part = " ".join(rendered_widgets[:3])
        time_part = " ".join(rendered_widgets[3:])
        output = """<span class="date_part">%(date_widget)s</span>
        <span class="time_part%(timezone)s">%(time_widget)s</span>""" % {
            "date_widget": date_part,
            "time_widget": time_part,
            "timezone": " tz" if settings.USE_TZ else "",
        }
        return output


class SelectDateTimeHiddenWidget(SelectDateTimeWidget):
    def __init__(self, attrs=None):
        widgets = (
            forms.HiddenInput(),
            forms.HiddenInput(),
            forms.HiddenInput(),
            forms.HiddenInput(),
            forms.HiddenInput(),
        )
        if settings.USE_TZ:
            widgets += (forms.HiddenInput(),)
        super(SelectDateTimeWidget, self).__init__(widgets, attrs)
