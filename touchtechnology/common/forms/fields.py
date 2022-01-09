from __future__ import unicode_literals

import json
import re
from datetime import date, datetime, time

import pytz
from django import forms
from django.conf import settings
from django.db.models import Min
from django.utils import timezone
from django.utils.encoding import smart_str
from django.utils.translation import gettext_lazy as _
from mptt.forms import TreeNodeChoiceField
from namedentities import named_entities

from touchtechnology.common.forms.iter import TemplateChoiceIterator
from touchtechnology.common.forms.mixins import LabelFromInstanceMixin
from touchtechnology.common.forms.widgets import (
    BootstrapGoogleMapsWidget,
    HTMLWidget,
    SelectDateHiddenWidget,
    SelectDateTimeHiddenWidget,
    SelectDateTimeWidget,
    SelectDateWidget,
    SelectTimeHiddenWidget,
    SelectTimeWidget,
)


class EmailField(forms.EmailField):
    """
    Custom EmailField which will transform email address to lowercase unless
    advised otherwise as this SHOULD NOT be significant.
    """

    def __init__(self, lowercase=True, *args, **kwargs):
        super(EmailField, self).__init__(*args, **kwargs)
        self.lowercase = lowercase

    def clean(self, data):
        data = super(EmailField, self).clean(data)
        if self.lowercase:
            data = data.lower()
        return data


class ModelMultipleChoiceField(LabelFromInstanceMixin, forms.ModelMultipleChoiceField):
    def __init__(self, select_related=True, *args, **kwargs):
        super(ModelMultipleChoiceField, self).__init__(*args, **kwargs)
        if select_related and self.queryset is not None:
            self.queryset = self.queryset.select_related()


class HTMLField(forms.CharField):
    widget = HTMLWidget

    def widget_attrs(self, widget):
        options = getattr(settings, "FROALA_EDITOR_OPTIONS", {})
        attrs = {
            "data-options": json.dumps(options),
        }
        return attrs

    def clean(self, value):
        if isinstance(value, str):
            value = named_entities(value)
        return super(HTMLField, self).clean(value)


class GoogleMapsField(forms.MultiValueField):
    def __init__(self, max_length, width=300, height=200, zoom=8, *args, **kwargs):
        fields = (
            forms.CharField(max_length=25, required=False),
            forms.CharField(max_length=25, required=False),
            forms.IntegerField(required=False),
        )
        kwargs["widget"] = BootstrapGoogleMapsWidget(height, width, zoom)
        super(GoogleMapsField, self).__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        return ",".join([smart_str(d) for d in data_list])

    def clean(self, data):
        if [d for d in data if d]:
            return ",".join(data)
        return super(GoogleMapsField, self).clean(data)


class SelectDateField(forms.MultiValueField):
    widget = SelectDateWidget
    hidden_widget = SelectDateHiddenWidget

    def __init__(self, *args, **kwargs):
        fields = (
            forms.IntegerField(required=False),
            forms.IntegerField(required=False),
            forms.IntegerField(required=False),
        )
        super(SelectDateField, self).__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        return date(data_list[2], data_list[1], data_list[0])

    def clean(self, data):
        if data is None:
            data = ["", "", ""]

        if not [d for d in data if d]:
            if self.required:
                raise forms.ValidationError("This field is required.")
            return None

        try:
            day, month, year = (int(i) for i in data)
            d = date(year, month, day)
        except ValueError:
            raise forms.ValidationError("Please enter a valid date.")
        return d


class SelectTimeField(forms.MultiValueField):
    widget = SelectTimeWidget
    hidden_widget = SelectTimeHiddenWidget

    def __init__(self, *args, **kwargs):
        fields = (
            forms.IntegerField(required=False),
            forms.IntegerField(required=False),
        )
        super(SelectTimeField, self).__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        return time(data_list[0], data_list[1])

    def clean(self, data):
        if not data:
            if self.required:
                raise forms.ValidationError("This field is required.")
            data = ("", "")

        t = None

        try:
            try:
                try:
                    hour, minute = data
                except ValueError:
                    raise forms.ValidationError(repr(data))

                try:
                    hour = int(hour)
                    assert 0 <= hour <= 23
                except (AssertionError, ValueError):
                    raise forms.ValidationError("Hour must be in 0..23")

                try:
                    minute = int(minute)
                    assert 0 <= minute <= 59
                except (AssertionError, ValueError):
                    raise forms.ValidationError("Minute must be in 0..59")

                try:
                    t = time(hour, minute)
                except ValueError as e:
                    raise forms.ValidationError(smart_str(e).capitalize())

            except TypeError as e:
                raise forms.ValidationError("Please enter a valid time.")

        except forms.ValidationError:
            if self.required or any(data):
                raise

        return t


class SelectDateTimeField(forms.MultiValueField):
    widget = SelectDateTimeWidget
    hidden_widget = SelectDateTimeHiddenWidget

    def __init__(self, *args, **kwargs):
        fields = (
            forms.IntegerField(required=False),
            forms.IntegerField(required=False),
            forms.IntegerField(required=False),
            forms.IntegerField(required=False),
            forms.IntegerField(required=False),
        )
        if settings.USE_TZ:
            fields += (forms.CharField(required=True),)
        super(SelectDateTimeField, self).__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        return date(
            data_list[2], data_list[1], data_list[0], data_list[3], data_list[4]
        )

    def clean(self, data):
        if data is None:
            data = ["", "", "", "", ""]

        if not [d for d in data if d]:
            if self.required:
                raise forms.ValidationError("This field is required.")
            return None

        try:
            day, month, year, hour, minute = (int(i) for i in data[:5])
            value = datetime(year, month, day, hour, minute)
            if settings.USE_TZ:
                try:
                    tzinfo = pytz.timezone(data[5])
                except IndexError:
                    raise forms.ValidationError("Please select a time zone.")
                except pytz.exceptions.UnknownTimeZoneError:
                    raise forms.ValidationError("Please select a valid time " "zone.")
                value = timezone.make_aware(value, tzinfo)
        except ValueError:
            raise forms.ValidationError("Please enter a valid date and time.")

        return value


class TemplatePathFormField(forms.ChoiceField):
    def __init__(
        self,
        template_base,
        template_folder,
        match=None,
        recursive=False,
        required=True,
        widget=None,
        label=None,
        initial=None,
        help_text=None,
        cache_choices=False,
        empty_label=_("Default"),
        # This will never be used, but it's now a CharField in the
        # database so we need to pull it out of the keyword
        # arguments.
        max_length=None,
        *args,
        **kwargs
    ):

        super(TemplatePathFormField, self).__init__(
            required=required,
            widget=widget,
            label=label,
            initial=initial,
            help_text=help_text,
            *args,
            **kwargs
        )

        self.template_base = template_base
        self.template_folder = template_folder
        self.match = match
        self.recursive = recursive
        self.empty_label = empty_label

        if self.match is not None:
            self.match_re = re.compile(self.match)

        if not self.template_base.endswith("/"):
            self.template_base += "/"

        self.widget.choices = self.choices

    def _get_choices(self):
        return TemplateChoiceIterator(self)

    choices = property(_get_choices, forms.ChoiceField._set_choices)


class ModelChoiceField(LabelFromInstanceMixin, forms.ModelChoiceField):
    def __init__(self, select_related=True, *args, **kwargs):
        super(ModelChoiceField, self).__init__(*args, **kwargs)
        if select_related and self.queryset is not None:
            self.queryset = self.queryset.select_related()


class SitemapNodeModelChoiceField(ModelChoiceField):
    def __init__(self, label_from_instance="title", *args, **kwargs):
        super(SitemapNodeModelChoiceField, self).__init__(
            label_from_instance=label_from_instance, *args, **kwargs
        )


def boolean_choice_field_coerce(value):
    return bool(int(value))


class MinTreeNodeChoiceField(TreeNodeChoiceField):
    @property
    def minimum_level(self):
        if not hasattr(self, "_minimum_level"):
            self._minimum_level = self.queryset.aggregate(minimum=Min("level")).get(
                "minimum"
            )
        return self._minimum_level

    def label_from_instance(self, obj):
        level = obj.level - self.minimum_level
        return "%s %s" % (self.level_indicator * level, smart_str(obj))
