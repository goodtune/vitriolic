import uuid

from django.db import models
from touchtechnology.common import fields
from touchtechnology.common.forms.fields import (
    EmailField as EmailFormField, GoogleMapsField, HTMLField as HTMLFormField, ModelChoiceField,
    ModelMultipleChoiceField, SelectDateField, SelectDateTimeField, SelectTimeField,
    SitemapNodeModelChoiceField, TemplatePathFormField,
)


class BooleanField(models.BooleanField):
    def formfield(self, **kwargs):
        defaults = {
            'form_class': fields.BooleanChoiceField,
        }
        defaults.update(kwargs)
        return super(BooleanField, self).formfield(**defaults)


class DateField(models.DateField):
    def formfield(self, form_class=SelectDateField, **kwargs):
        return super(DateField, self).formfield(
            form_class=form_class, **kwargs)


class EmailField(models.EmailField):
    """
    Custom EmailField which defaults to a length of 254 to be compliant with
    RFCs 3696 and 5321. Also will transform email address to lowercase unless
    advised otherwise as this SHOULD NOT be significant.
    """
    def __init__(self, max_length=254, lowercase=True, *args, **kwargs):
        super(EmailField, self).__init__(max_length=max_length,
                                         *args, **kwargs)
        self.lowercase = lowercase

    def clean(self, value, model_instance):
        value = super(EmailField, self).clean(value, model_instance)
        if self.lowercase:
            value = value.lower()
        return value

    def formfield(self, form_class=EmailFormField, **kwargs):
        return super(EmailField, self).formfield(
            form_class=form_class, lowercase=self.lowercase, **kwargs)


class TimeField(models.TimeField):
    def formfield(self, form_class=SelectTimeField, **kwargs):
        return super(TimeField, self).formfield(
            form_class=form_class, **kwargs)


class DateTimeField(models.DateTimeField):
    def formfield(self, form_class=SelectDateTimeField, **kwargs):
        return super(DateTimeField, self).formfield(
            form_class=form_class, **kwargs)

    def to_python(self, value):
        # See #13. When turning the database serialized value back into
        # a Python datetime if the value is '' or null an exception was
        # being raised. Explicitly check for these situations.
        if not value and (self.blank or self.null):
            return None
        return super(DateTimeField, self).to_python(value)


class LocationField(models.CharField):
    def formfield(self, form_class=GoogleMapsField, **kwargs):
        return super(LocationField, self).formfield(
            form_class=form_class, **kwargs)


class HTMLField(models.TextField):
    """
    A large string field for HTML content. It uses a custom widget in
    forms, and converts unicode characters to XML entities.
    """
    def formfield(self, form_class=HTMLFormField, widget=HTMLFormField.widget,
                  **kwargs):
        return super(HTMLField, self).formfield(
            form_class=form_class, widget=widget, **kwargs)


class ForeignKey(models.ForeignKey):
    def __init__(self, to, label_from_instance='name', *args, **kwargs):
        super(ForeignKey, self).__init__(to, *args, **kwargs)
        self.label_from_instance = label_from_instance

    def formfield(self, form_class=ModelChoiceField, **kwargs):
        kwargs.setdefault('label_from_instance', self.label_from_instance)
        return super(ForeignKey, self).formfield(
            form_class=form_class, **kwargs)


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
        super(ManyToManyField, self).__init__(to, *args, **kwargs)
        self.label_from_instance = label_from_instance

    def formfield(self, form_class=ModelMultipleChoiceField, **kwargs):
        kwargs.setdefault('label_from_instance', self.label_from_instance)
        return super(ManyToManyField, self).formfield(
            form_class=form_class, **kwargs)


class NodeOneToOneField(models.OneToOneField):
    """
    Use when your OneToOneField has it's title on the SitemapNode.

    Purely aesthetic - gives us nicer labels in the default django admin.
    """
    def formfield(self, form_class=SitemapNodeModelChoiceField, **kwargs):
        return super(NodeOneToOneField, self).formfield(
            form_class=form_class, **kwargs)


class NodeForeignKey(models.ForeignKey):
    """
    Use when your ForeignKey has it's title on the SitemapNode.

    Purely aesthetic - gives us nicer labels in the default django admin.
    """
    def formfield(self, form_class=SitemapNodeModelChoiceField, **kwargs):
        return super(NodeForeignKey, self).formfield(
            form_class=form_class, **kwargs)


class TemplatePathField(models.CharField):
    """
    Field heavily based on `FilePathField` but designed to be able to accept
    custom templates from either the filesystem (as per `FilePathField`) or
    from the database by making use of our localised version of
    `django-dbtemplates`.
    """
    def __init__(self, verbose_name=None, name=None, template_base='',
                 template_folder='', match=None, recursive=False,
                 *args, **kwargs):
        self.template_base = template_base
        self.template_folder = template_folder
        self.match = match
        self.recursive = recursive
        super(TemplatePathField, self).__init__(verbose_name, name, **kwargs)

    def formfield(self, **kwargs):
        defaults = {
            'template_base': self.template_base,
            'template_folder': self.template_folder,
            'match': self.match,
            'recursive': self.recursive,
            'form_class': TemplatePathFormField,
        }
        defaults.update(kwargs)
        return super(TemplatePathField, self).formfield(**defaults)

    def get_internal_type(self):
        return "FilePathField"


class UUIDField(models.CharField):

    def __init__(self, verbose_name=None, name=None, auto=False, **kwargs):
        self.auto = auto
        # Fixed length, we're storing the UUIDs as text.
        kwargs['max_length'] = 36
        if auto:
            # Do not let the user edit UUIDs if they are auto assigned
            kwargs['editable'] = False
            kwargs['blank'] = True
        super(UUIDField, self).__init__(verbose_name, name, **kwargs)

    def pre_save(self, model_instance, add):
        value = super(UUIDField, self).pre_save(model_instance, add)
        if not value and self.auto:
            value = str(uuid.uuid1())
            setattr(model_instance, self.attname, value)
        return value
