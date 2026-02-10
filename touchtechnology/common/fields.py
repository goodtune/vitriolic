import json
import logging
import os.path
import re
import uuid
from datetime import datetime
from importlib import metadata

from constance import config
from django import forms
from django.db import models
from django.forms.widgets import DateInput, MultiWidget, Select, TimeInput
from django.utils import timezone
from django.utils.encoding import smart_str
from django.utils.translation import gettext_lazy as _
from froala_editor.widgets import FroalaEditor
from namedentities import named_entities
from timezone_field import TimeZoneFormField
from timezone_field.backends import get_tz_backend
from timezone_field.choices import with_gmt_offset

logger = logging.getLogger(__name__)


# ============================================================================
# Section 1: Helper Functions
# ============================================================================


def boolean_coerce(value):
    if value in {1, "1"}:
        return True
    if value in {0, "0"}:
        return False


def boolean_choice_field_coerce(value):
    return bool(int(value))


# ============================================================================
# Section 2: Widgets
# ============================================================================


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


# ============================================================================
# Section 3: Mixins
# ============================================================================


class LabelFromInstanceMixin(object):
    def __init__(self, label_from_instance="name", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._label_from_instance = label_from_instance

    def label_from_instance(self, obj):
        if isinstance(self._label_from_instance, str):
            value = getattr(obj, self._label_from_instance)
        elif callable(self._label_from_instance):
            value = self._label_from_instance(obj)
        else:
            value = obj
        if callable(value):
            try:
                value = value(obj)
            except TypeError:
                value = value()
        return smart_str(value)


# ============================================================================
# Section 4: Iterators
# ============================================================================


class TemplateChoiceIterator(object):
    def __init__(self, field):
        self.field = field

    def __iter__(self):
        # Evaluate SimpleLazyObjects once at start to prevent changes during iteration
        template_base = str(self.field.template_base)
        template_folder = str(self.field.template_folder)
        folder = os.path.join(template_base, template_folder)
        choices = []
        if self.field.recursive:
            for root, dirs, files in os.walk(folder):
                for f in files:
                    if self.field.match is None or self.field.match_re.search(f):
                        f = os.path.join(root, f)
                        base = f.replace(template_base, "")
                        choices.append((base, f.replace(folder, "", 1)))
        else:
            try:
                for f in os.listdir(folder):
                    full_file = os.path.join(folder, f)
                    if os.path.isfile(full_file) and (
                        self.field.match is None or self.field.match_re.search(f)
                    ):
                        choices.append((full_file, f))
            except OSError:
                pass

        if not self.field.required:
            yield ("", self.field.empty_label)

        if choices:
            yield ("Static template", choices)

    def choice(self, obj):
        path = obj.path.replace(str(self.field.template_folder), "", 1)
        return (obj.path, "%s (%s)" % (path, obj.name))


# ============================================================================
# Section 5: Form Fields
# ============================================================================


class BooleanChoiceField(forms.TypedChoiceField):
    widget = forms.Select

    def __init__(self, *args, **kwargs):
        defaults = {
            "choices": [
                ("1", _("Yes")),
                ("0", _("No")),
            ],
            "coerce": boolean_coerce,
            "required": True,
        }
        defaults.update(kwargs)
        super().__init__(*args, **defaults)

    def prepare_value(self, value):
        if value is not None:
            return str(int(value))


class EmailFormField(forms.EmailField):
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


class HTMLFormField(forms.CharField):
    widget = HTMLWidget

    def widget_attrs(self, widget):
        options = config.FROALA_EDITOR_OPTIONS
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
        self._match_re = None

        if not self.template_base.endswith("/"):
            self.template_base += "/"

        self.widget.choices = self.choices

    @property
    def match_re(self):
        """Lazy compilation of match regex to handle SimpleLazyObject."""
        if self._match_re is None and self.match is not None:
            # Force evaluation of lazy objects
            match_str = str(self.match)
            self._match_re = re.compile(match_str)
        return self._match_re

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


# ============================================================================
# Section 6: Model Fields
# ============================================================================


class BooleanField(models.BooleanField):
    def formfield(self, **kwargs):
        defaults = {
            "form_class": BooleanChoiceField,
        }
        defaults.update(kwargs)
        return super().formfield(**defaults)


class DateField(models.DateField): ...


class EmailField(models.EmailField):
    """
    Custom EmailField which defaults to a length of 254 to be compliant with
    RFCs 3696 and 5321. Also will transform email address to lowercase unless
    advised otherwise as this SHOULD NOT be significant.
    """

    def __init__(self, max_length=254, lowercase=True, *args, **kwargs):
        super().__init__(max_length=max_length, *args, **kwargs)
        self.lowercase = lowercase

    def clean(self, value, model_instance):
        value = super().clean(value, model_instance)
        if self.lowercase:
            value = value.lower()
        return value

    def formfield(self, form_class=EmailFormField, **kwargs):
        return super().formfield(
            form_class=form_class, lowercase=self.lowercase, **kwargs
        )


class TimeField(models.TimeField): ...


class DateTimeField(models.DateTimeField):
    def formfield(self, form_class=SelectDateTimeField, **kwargs):
        return super().formfield(form_class=form_class, **kwargs)


class LocationField(models.CharField):
    def formfield(self, form_class=GoogleMapsField, **kwargs):
        return super().formfield(form_class=form_class, **kwargs)


class HTMLField(models.TextField):
    """
    A large string field for HTML content. It uses a custom widget in
    forms, and converts unicode characters to XML entities.
    """

    def formfield(
        self, form_class=HTMLFormField, widget=HTMLFormField.widget, **kwargs
    ):
        return super().formfield(form_class=form_class, widget=widget, **kwargs)


class ForeignKey(models.ForeignKey):
    def __init__(self, to, label_from_instance="name", *args, **kwargs):
        super().__init__(to, *args, **kwargs)
        self.label_from_instance = label_from_instance

    def formfield(self, form_class=ModelChoiceField, **kwargs):
        kwargs.setdefault("label_from_instance", self.label_from_instance)
        return super().formfield(form_class=form_class, **kwargs)


class ManyToManyField(models.ManyToManyField):
    """
    Custom `ManyToManyField` which overrides the formfield to use the
    much nicer `CheckboxSelectMultiple` widget instead of a multiple
    select list box.
    """

    def __init__(self, to, label_from_instance=None, *args, **kwargs):
        """
        Custom `__init__` because I don't want the 'Hold down "Control"...'
        message since I'm using the `CheckboxSelectMultiple` widget.
        """
        super().__init__(to, *args, **kwargs)
        self.label_from_instance = label_from_instance

    def formfield(self, form_class=ModelMultipleChoiceField, **kwargs):
        kwargs.setdefault("label_from_instance", self.label_from_instance)
        return super().formfield(form_class=form_class, **kwargs)


class NodeOneToOneField(models.OneToOneField):
    """
    Use when your OneToOneField has it's title on the SitemapNode.

    Purely aesthetic - gives us nicer labels in the default django admin.
    """

    def formfield(self, form_class=SitemapNodeModelChoiceField, **kwargs):
        return super().formfield(form_class=form_class, **kwargs)


class NodeForeignKey(models.ForeignKey):
    """
    Use when your ForeignKey has it's title on the SitemapNode.

    Purely aesthetic - gives us nicer labels in the default django admin.
    """

    def formfield(self, form_class=SitemapNodeModelChoiceField, **kwargs):
        return super().formfield(form_class=form_class, **kwargs)


class TemplatePathField(models.CharField):
    """
    Field heavily based on `FilePathField` but designed to be able to accept
    custom templates from either the filesystem (as per `FilePathField`) or
    from the database by making use of our localised version of
    `django-dbtemplates`.
    """

    def __init__(
        self,
        verbose_name=None,
        name=None,
        template_base="",
        template_folder="",
        match=None,
        recursive=False,
        *args,
        **kwargs,
    ):
        self.template_base = template_base
        self.template_folder = template_folder
        self.match = match
        self.recursive = recursive
        super().__init__(verbose_name, name, **kwargs)

    def formfield(self, **kwargs):
        defaults = {
            "template_base": self.template_base,
            "template_folder": self.template_folder,
            "match": self.match,
            "recursive": self.recursive,
            "form_class": TemplatePathFormField,
        }
        defaults.update(kwargs)
        return super().formfield(**defaults)

    def get_internal_type(self):
        return "FilePathField"


class UUIDField(models.CharField):
    def __init__(self, verbose_name=None, name=None, auto=False, **kwargs):
        self.auto = auto
        # Fixed length, we're storing the UUIDs as text.
        kwargs["max_length"] = 36
        if auto:
            # Do not let the user edit UUIDs if they are auto assigned
            kwargs["editable"] = False
            kwargs["blank"] = True
        super().__init__(verbose_name, name, **kwargs)

    def pre_save(self, model_instance, add):
        value = super().pre_save(model_instance, add)
        if not value and self.auto:
            value = str(uuid.uuid1())
            setattr(model_instance, self.attname, value)
        return value
