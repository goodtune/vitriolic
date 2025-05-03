import json
import re
from datetime import datetime

from django import forms
from django.conf import settings
from django.db.models import Min
from django.utils import timezone
from django.utils.encoding import smart_str
from django.utils.translation import gettext_lazy as _
from mptt.forms import TreeNodeChoiceField
from namedentities import named_entities
from timezone_field import TimeZoneFormField

from touchtechnology.common.forms.iter import TemplateChoiceIterator
from touchtechnology.common.forms.mixins import LabelFromInstanceMixin
from touchtechnology.common.forms.widgets import (
    GoogleMapsWidget,
    HTMLWidget,
    SelectDateTimeHiddenWidget,
    SelectDateTimeWidget,
)


class EmailField(forms.EmailField):
    """
    Custom EmailField which will transform email address to lowercase unless
    advised otherwise as this SHOULD NOT be significant.
    """

    def __init__(self, lowercase=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lowercase = lowercase

    def clean(self, data):
        data = super().clean(data)
        if self.lowercase:
            data = data.lower()
        return data


class ModelMultipleChoiceField(LabelFromInstanceMixin, forms.ModelMultipleChoiceField):
    def __init__(self, select_related=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if select_related and self.queryset is not None:
            self.queryset = self.queryset.select_related()


class HTMLField(forms.CharField):
    widget = HTMLWidget

    def widget_attrs(self, widget):
        options = getattr(settings, "FROALA_EDITOR_OPTIONS", {})
        return {"data-options": json.dumps(options)}

    def clean(self, value):
        if isinstance(value, str):
            value = named_entities(value)
        return super().clean(value)


class GoogleMapsField(forms.MultiValueField):
    def __init__(self, max_length, width=300, height=200, zoom=8, *args, **kwargs):
        fields = (
            forms.CharField(max_length=25, required=False),
            forms.CharField(max_length=25, required=False),
            forms.IntegerField(required=False),
        )
        kwargs["widget"] = GoogleMapsWidget(height, width, zoom)
        super().__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        return ",".join([smart_str(each) for each in data_list])

    def clean(self, data):
        if [d for d in data if d]:
            return ",".join(data)
        return super().clean(data)


class SelectDateTimeField(forms.MultiValueField):
    widget = SelectDateTimeWidget
    hidden_widget = SelectDateTimeHiddenWidget
    default_error_messages = {
        "invalid_date": _("Enter a valid date."),
        "invalid_time": _("Enter a valid time."),
        "invalid_tz": _("Enter a valid time zone."),
    }

    def __init__(self, *, input_date_formats=None, input_time_formats=None, **kwargs):
        errors = self.default_error_messages.copy()
        if "error_messages" in kwargs:
            errors.update(kwargs["error_messages"])
        localize = kwargs.get("localize", False)
        fields = (
            forms.DateField(
                input_formats=input_date_formats,
                error_messages={"invalid": errors["invalid_date"]},
                localize=localize,
            ),
            forms.TimeField(
                input_formats=input_time_formats,
                error_messages={"invalid": errors["invalid_time"]},
                localize=localize,
            ),
            TimeZoneFormField(
                use_pytz=False,
                choices_display="WITH_GMT_OFFSET",
                error_messages={"required": errors["invalid_tz"]},
            ),
        )
        super().__init__(fields, **kwargs)

    def compress(self, data_list):
        if data_list:
            # Raise a validation error if time or date is empty
            # (possible if SplitDateTimeField has required=False).
            if data_list[0] in self.empty_values:
                raise forms.ValidationError(
                    self.error_messages["invalid_date"], code="invalid_date"
                )
            if data_list[1] in self.empty_values:
                raise forms.ValidationError(
                    self.error_messages["invalid_time"], code="invalid_time"
                )
            if data_list[2] in self.empty_values:
                raise forms.ValidationError(
                    self.error_messages["invalid_tz"], code="invalid_tz"
                )
            result = datetime.combine(*data_list[:-1])
            return timezone.make_aware(result, data_list[-1])
        return None


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
        **kwargs,
    ):
        super().__init__(
            required=required,
            widget=widget,
            label=label,
            initial=initial,
            help_text=help_text,
            *args,
            **kwargs,
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

    choices = property(_get_choices, forms.ChoiceField.choices.fset)


class ModelChoiceField(LabelFromInstanceMixin, forms.ModelChoiceField):
    def __init__(self, select_related=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if select_related and self.queryset is not None:
            self.queryset = self.queryset.select_related()


class SitemapNodeModelChoiceField(ModelChoiceField):
    def __init__(self, label_from_instance="title", *args, **kwargs):
        super().__init__(label_from_instance=label_from_instance, *args, **kwargs)


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
        return f"{self.level_indicator * (obj.level - self.minimum_level)} {smart_str(obj)}"
