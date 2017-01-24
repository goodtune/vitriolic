import json
import logging
import os.path
import re
from datetime import date, datetime, time
from operator import itemgetter

import pytz
import six
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.forms.formsets import formset_factory
from django.forms.utils import flatatt
from django.forms.widgets import (
    CheckboxFieldRenderer, CheckboxSelectMultiple, ChoiceFieldRenderer,
    MultiWidget as MWB, SelectMultiple,
)
from django.utils import timezone
from django.utils.encoding import smart_str
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _
from froala_editor.widgets import FroalaEditor
from guardian.models import GroupObjectPermission, UserObjectPermission
from guardian.shortcuts import assign_perm, remove_perm
from touchtechnology.common.mixins import BootstrapFormControlMixin
from touchtechnology.common.utils import timezone_choices

logger = logging.getLogger(__name__)


def groups_widget(f):
    return forms.CheckboxSelectMultiple(choices=f.choices)


class MultiWidget(MWB):

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
            attrs.pop('required', None)
        return attrs


class RadioChoiceInput(forms.widgets.RadioChoiceInput):
    def render(self, name=None, value=None, attrs=None, choices=()):
        if self.id_for_label:
            label_for = format_html(' for="{0}"', self.id_for_label)
        else:
            label_for = ''
        # The special sauce is to use smart_str, on tracing it was found that
        # format_html was returning SafeBytes whereas the implementation on the
        # super class was returning SafeText.
        return smart_str(
            format_html('<label{0} class="radio-inline">{1} {2}</label>',
                        label_for, self.tag(), self.choice_label))

    def tag(self):
        final_attrs = dict(self.attrs, type=self.input_type,
                           name=self.name, value=self.choice_value)
        if self.is_checked():
            final_attrs['checked'] = 'checked'
        return format_html('<input{0} />', flatatt(final_attrs))


class RadioFieldRenderer(forms.widgets.RadioFieldRenderer):
    choice_input_class = RadioChoiceInput

    def render(self):
        self.attrs.setdefault('class', 'ui-icheck')
        start_tag = '<div class="icheck">'
        output = [start_tag]
        for i, choice in enumerate(self.choices):
            w = self.choice_input_class(self.name, self.value,
                                        self.attrs.copy(), choice, i)
            output.append(smart_str(w))
        output.append('</div>')
        return mark_safe('\n'.join(output))


class LabelFromInstanceMixin(object):
    def __init__(self, label_from_instance='name', *args, **kwargs):
        super(LabelFromInstanceMixin, self).__init__(*args, **kwargs)
        self._label_from_instance = label_from_instance

    def label_from_instance(self, obj):
        if isinstance(self._label_from_instance, six.string_types):
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


def boolean_choice_field_coerce(value):
    return bool(int(value))


class BooleanSelect(forms.RadioSelect):
    renderer = RadioFieldRenderer

    def render(self, name, value, *args, **kwargs):
        value = int(value or '0')
        return super(BooleanSelect, self).render(name, value, *args, **kwargs)


class BooleanChoiceField(forms.TypedChoiceField):
    widget = BooleanSelect

    def __init__(self, positive_label=_('Yes'), negative_label=_('No'),
                 *args, **kwargs):
        super(BooleanChoiceField, self).__init__(
            choices=((1, positive_label), (0, negative_label)),
            coerce=boolean_choice_field_coerce,
            *args, **kwargs)


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


class ModelMultipleChoiceField(LabelFromInstanceMixin,
                               forms.ModelMultipleChoiceField):
    widget = forms.CheckboxSelectMultiple

    def __init__(self, select_related=True, *args, **kwargs):
        super(ModelMultipleChoiceField, self).__init__(*args, **kwargs)
        if select_related and self.queryset is not None:
            self.queryset = self.queryset.select_related()


class EmailAuthenticationForm(BootstrapFormControlMixin, AuthenticationForm):
    username = EmailField(label=_('Email Address'))

    def __init__(self, *args, **kwargs):
        super(EmailAuthenticationForm, self).__init__(*args, **kwargs)
        for field_name in self.fields:
            self.fields[field_name].widget.attrs['class'] += ' text-center'


class HTMLWidget(FroalaEditor):

    def trigger_froala(self, el_id, options):
        """
        We don't want to do inline scripts, we'll handle the loading once from
        froala.js, so return an empty string to overload the base FroalaEditor
        implementation.
        """
        return u''

    class Media:
        css = {
            'all': (
                'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.3.0/'
                'codemirror.min.css',
                'touchtechnology/common/css/froala_themes/dark.min.css',
                'touchtechnology/common/css/froala_themes/gray.min.css',
                'touchtechnology/common/css/froala_themes/red.min.css',
                'touchtechnology/common/css/froala_themes/royal.min.css',
            ),
        }
        js = (
            'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.3.0/'
            'codemirror.min.js',
            'touchtechnology/common/js/froala.js',
        )


class HTMLField(forms.CharField):
    widget = HTMLWidget

    def widget_attrs(self, widget):
        options = getattr(settings, 'FROALA_EDITOR_OPTIONS', {})
        attrs = {
            'data-options': json.dumps(options),
        }
        return attrs

    def clean(self, value):
        if isinstance(value, six.string_types):
            value = value.encode('ascii', 'xmlcharrefreplace')
        return super(HTMLField, self).clean(value)


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
            return value.split(',')
        return ('', '', '')

    def render(self, *args, **kwargs):
        res = super(GoogleMapsWidget, self).render(*args, **kwargs)
        return u'<div class="mapwidget">' + res + u'</div>'

    class Media:
        css = {
            'all': ('touchtechnology/common/css/location_widget.css',)
        }
        js = (
            '//maps.googleapis.com/maps/api/js?v=3',
            'touchtechnology/common/js/location_widget.js',
        )


class BootstrapGoogleMapsWidget(GoogleMapsWidget):
    def render(self, *args, **kwargs):
        base = super(BootstrapGoogleMapsWidget, self).render(*args, **kwargs)
        return u'''
            <div class="form-group">
                <label class="control-label col-sm-3">%s</label>
                <div class="col-sm-7">%s</div>
            </div>
        ''' % (_("Location"), base)


class GoogleMapsField(forms.MultiValueField):
    def __init__(self, max_length, width=300, height=200, zoom=8,
                 *args, **kwargs):
        fields = (
            forms.CharField(max_length=25, required=False),
            forms.CharField(max_length=25, required=False),
            forms.IntegerField(required=False),
        )
        kwargs['widget'] = BootstrapGoogleMapsWidget(height, width, zoom)
        super(GoogleMapsField, self).__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        return ','.join([smart_str(d) for d in data_list])

    def clean(self, data):
        if [d for d in data if d]:
            return ','.join(data)
        return super(GoogleMapsField, self).clean(data)


DAY_CHOICES = [('', '')] + list(zip(*[range(1, 32)] * 2))

MONTH_CHOICES = (
    ('', ''),
    (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'), (5, 'May'),
    (6, 'June'), (7, 'July'), (8, 'August'), (9, 'September'), (10, 'October'),
    (11, 'November'), (12, 'December'),
)

HOUR_CHOICES = [('', '')] + list(zip(*[range(0, 24, 1)] * 2))

MINUTES = range(0, 60)
MINUTE_CHOICES = [('', '')] + list(zip(MINUTES, ['%02d' % m for m in MINUTES]))

TIMEZONE_CHOICES = list(timezone_choices(
    pytz.country_names, pytz.country_timezones, itemgetter(1)))

# Add UTC and MGT
TIMEZONE_CHOICES.insert(1, (_('Universal'), [
    ('UTC', _("Coordinated Universal Time")),
    ('GMT', _("Greenwich Mean Time")),
]))


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
            data = ['', '', '']

        if not [d for d in data if d]:
            if self.required:
                raise forms.ValidationError('This field is required.')
            return None

        try:
            day, month, year = map(int, data)
            d = date(year, month, day)
        except ValueError:
            raise forms.ValidationError('Please enter a valid date.')
        return d


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
                raise forms.ValidationError('This field is required.')
            data = ('', '')

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
                    raise forms.ValidationError('Hour must be in 0..23')

                try:
                    minute = int(minute)
                    assert 0 <= minute <= 59
                except (AssertionError, ValueError):
                    raise forms.ValidationError('Minute must be in 0..59')

                try:
                    t = time(hour, minute)
                except ValueError as e:
                    raise forms.ValidationError(smart_str(e).capitalize())

            except TypeError as e:
                raise forms.ValidationError('Please enter a valid time.')

        except forms.ValidationError:
            if self.required or any(data):
                raise

        return t


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
            widgets += (
                forms.Select(choices=TIMEZONE_CHOICES, attrs=attrs),
            )
        super(SelectDateTimeWidget, self).__init__(widgets, attrs)

    def decompress(self, value):
        if settings.USE_TZ:
            tzinfo = timezone.get_current_timezone()
            tzname = timezone.get_current_timezone_name()
            logger.debug('USE_TZ is True, timezone is %s (%s)',
                         tzinfo, tzname)

            if value:
                logger.debug('Value is set (%s)', value)
                if timezone.is_naive(value):
                    value = timezone.make_aware(
                        value, timezone.get_default_timezone())
                    logger.debug('Naive value, set default timezone (%s)',
                                 value)
                value = value.astimezone(tzinfo)
                logger.debug('Ensure timezone is correctly set to %s (%s)',
                             tzname, value)
                values = (value.day, value.month, value.year,
                          value.hour, value.minute, tzname)
            else:
                values = (None, None, None, None, None, None)

        elif value:
            values = (value.day, value.month, value.year,
                      value.hour, value.minute)

        else:
            values = (None, None, None, None, None)

        return values

    def format_output(self, rendered_widgets):
        date_part = " ".join(rendered_widgets[:3])
        time_part = " ".join(rendered_widgets[3:])
        output = """<span class="date_part">%(date_widget)s</span>
        <span class="time_part%(timezone)s">%(time_widget)s</span>""" % {
            'date_widget': date_part,
            'time_widget': time_part,
            'timezone': ' tz' if settings.USE_TZ else '',
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
            widgets += (
                forms.HiddenInput(),
            )
        super(SelectDateTimeWidget, self).__init__(widgets, attrs)


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
            fields += (
                forms.CharField(required=True),
            )
        super(SelectDateTimeField, self).__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        return date(data_list[2], data_list[1], data_list[0],
                    data_list[3], data_list[4])

    def clean(self, data):
        if data is None:
            data = ['', '', '', '', '']

        if not [d for d in data if d]:
            if self.required:
                raise forms.ValidationError('This field is required.')
            return None

        try:
            day, month, year, hour, minute = map(int, data[:5])
            value = datetime(year, month, day, hour, minute)
            if settings.USE_TZ:
                try:
                    tzinfo = pytz.timezone(data[5])
                except IndexError:
                    raise forms.ValidationError('Please select a time zone.')
                except pytz.exceptions.UnknownTimeZoneError:
                    raise forms.ValidationError('Please select a valid time '
                                                'zone.')
                value = timezone.make_aware(value, tzinfo)
        except ValueError:
            raise forms.ValidationError('Please enter a valid date and time.')

        return value


class TemplateChoiceIterator(object):
    def __init__(self, field):
        self.field = field

    def __iter__(self):
        folder = os.path.join(self.field.template_base,
                              self.field.template_folder)
        choices = []
        if self.field.recursive:
            for root, dirs, files in os.walk(folder):
                for f in files:
                    if self.field.match is None or \
                       self.field.match_re.search(f):
                        f = os.path.join(root, f)
                        base = f.replace(self.field.template_base, '')
                        choices.append((base, f.replace(folder, '', 1)))
        else:
            try:
                for f in os.listdir(folder):
                    full_file = os.path.join(folder, f)
                    if os.path.isfile(full_file) and \
                            (self.field.match is None or
                             self.field.match_re.search(f)):
                        choices.append((full_file, f))
            except OSError:
                pass

        if not self.field.required:
            yield (u"", self.field.empty_label)

        if choices:
            yield ('Static template', choices)

    def choice(self, obj):
        path = obj.path.replace(self.field.template_folder, '', 1)
        return (obj.path, '%s (%s)' % (path, obj.name))


class TemplatePathFormField(forms.ChoiceField):
    def __init__(self, template_base, template_folder, match=None,
                 recursive=False, required=True, widget=None, label=None,
                 initial=None, help_text=None, cache_choices=False,
                 empty_label=_(u"Default"),
                 # This will never be used, but it's now a CharField in the
                 # database so we need to pull it out of the keyword
                 # arguments.
                 max_length=None,
                 *args, **kwargs):

        super(TemplatePathFormField, self).__init__(required=required,
                                                    widget=widget, label=label,
                                                    initial=initial,
                                                    help_text=help_text,
                                                    *args, **kwargs)

        self.template_base = template_base
        self.template_folder = template_folder
        self.match = match
        self.recursive = recursive
        self.empty_label = empty_label

        if self.match is not None:
            self.match_re = re.compile(self.match)

        if not self.template_base.endswith('/'):
            self.template_base += '/'

        self.widget.choices = self.choices

    def _get_choices(self):
        return TemplateChoiceIterator(self)

    choices = property(_get_choices, forms.ChoiceField._set_choices)


class SelectTimezoneForm(forms.Form):
    """
    Used by touchtechnology.common.context_processors.tz to generate a
    dropdown list of timezones to be used with the TimeZone middleware and
    set-timezone view.
    """
    timezone = forms.ChoiceField(choices=TIMEZONE_CHOICES,
                                 initial=timezone.get_current_timezone)


class UserMixin(BootstrapFormControlMixin):
    """
    Mixin class to be used in forms that need a `User` object passed in.
    """
    def __init__(self, user=None, *args, **kwargs):
        self.user = user
        super(UserMixin, self).__init__(*args, **kwargs)


class SuperUserSlugMixin(UserMixin):
    """
    Mixin class that will attempt to remove a field named `slug` from the
    form if the user cannot be identified, or if they are not a superuser.

    Handy for allowing advanced users to have finer control over the slug
    of a page, while providing default behaviour for regular users.
    """
    def __init__(self, *args, **kwargs):
        super(SuperUserSlugMixin, self).__init__(*args, **kwargs)
        if self.user is None or not self.user.is_superuser:
            self.fields.pop('slug', None)
            self.fields.pop('slug_locked', None)
        else:
            self.fields['slug'].required = False
            self.fields['slug'].help_text = _("If left blank, this will "
                                              "be automatically set based "
                                              "on the title.")


class RedefineModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(RedefineModelForm, self).__init__(*args, **kwargs)
        for field, _kw in self.Meta.redefine:
            kw = {}
            for key, val in _kw.items():
                if callable(val) and not type(val) == type:
                    kw[key] = val(self.fields[field])
                else:
                    kw[key] = val
            model_field = self.Meta.model._meta.get_field(field)
            self.fields[field] = model_field.formfield(**kw)


class ModelChoiceField(LabelFromInstanceMixin, forms.ModelChoiceField):

    def __init__(self, select_related=True, *args, **kwargs):
        super(ModelChoiceField, self).__init__(*args, **kwargs)
        if select_related and self.queryset is not None:
            self.queryset = self.queryset.select_related()


class SitemapNodeModelChoiceField(ModelChoiceField):
    def __init__(self, label_from_instance='title', *args, **kwargs):
        super(SitemapNodeModelChoiceField, self).__init__(
            label_from_instance=label_from_instance, *args, **kwargs)


class RegistrationForm(forms.Form):
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)
    email = EmailField()
    password1 = forms.CharField(widget=forms.PasswordInput,
                                label=_('Password'))
    password2 = forms.CharField(widget=forms.PasswordInput,
                                label=_('Password (again)'))

    def clean_email(self):
        UserModel = get_user_model()
        email = self.cleaned_data.get('email')
        if UserModel.objects.filter(email__iexact=email):
            raise forms.ValidationError(_("This email address is already in "
                                          "use. Please supply a different "
                                          "email address."))
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError(_("The two password fields "
                                              "didn't match."))
        return password2


###################
# django-guardian #
###################

class iCheckFieldRenderer(CheckboxFieldRenderer):
    def render(self):
        """
        Outputs a <div> for this set of choice fields.
        If an id was given to the field, it is applied to the <div> (each item
        in the list will get an id of `$id_$i`).
        """
        id_ = self.attrs.get('id', None)
        if id_:
            start_tag = format_html('<div class="icheck" id="{0}">', id_)
        else:
            start_tag = '<div class="icheck">'
        output = [start_tag]
        for i, choice in enumerate(self.choices):
            choice_value, choice_label = choice
            if isinstance(choice_label, (tuple, list)):
                attrs_plus = self.attrs.copy()
                if id_:
                    attrs_plus['id'] += '_{0}'.format(i)
                sub_ul_renderer = ChoiceFieldRenderer(name=self.name,
                                                      value=self.value,
                                                      attrs=attrs_plus,
                                                      choices=choice_label)
                sub_ul_renderer.choice_input_class = self.choice_input_class
                output.append(
                    format_html('<div class="checkbox">{0}{1}</div>',
                                choice_value, sub_ul_renderer.render()))
            else:
                # re-unpack the choice and handle HTML entities
                choice_value, choice_label = choice
                choice = (choice_value, mark_safe(
                    choice_label.encode('ascii', errors='xmlcharrefreplace')))
                w = self.choice_input_class(self.name, self.value,
                                            self.attrs.copy(), choice, i)
                output.append(format_html('<div class="checkbox">{0}</div>',
                                          smart_str(w)))
        output.append('</div>')
        return mark_safe('\n'.join(output))


class iCheckSelectMultiple(CheckboxSelectMultiple):
    renderer = iCheckFieldRenderer


class iCheckModelMultipleChoiceField(ModelMultipleChoiceField):
    widget = iCheckSelectMultiple


class PermissionForm(forms.ModelForm):
    """
    Generic form to be used to assign row-level permissions to an object.
    """
    widget = iCheckSelectMultiple
    staff_only = True
    max_checkboxes = 7  # Set based on number of rows visible in MVP layout

    def __init__(self, permission, *args, **kwargs):
        super(PermissionForm, self).__init__(*args, **kwargs)
        self.content_type = ContentType.objects.get_for_model(self.instance)
        self.permission = permission

        # determine if we should filter to only show staff
        user_queryset = get_user_model().objects.all()
        if self.staff_only:
            user_queryset = user_queryset.filter(is_staff=True)

        if user_queryset.count() <= self.max_checkboxes:
            user_widget = self.widget
        else:
            user_widget = SelectMultiple

        group_queryset = Group.objects.all()

        if group_queryset.count() <= self.max_checkboxes:
            group_widget = self.widget
        else:
            group_widget = SelectMultiple

        self.fields['users'] = ModelMultipleChoiceField(
            queryset=user_queryset,
            required=False,
            initial=self._users_with_perms,
            label_from_instance=lambda o: o.get_full_name(),
            widget=user_widget,
        )
        self.fields['users'].widget.attrs.setdefault('class', 'form-control')

        self.fields['groups'] = ModelMultipleChoiceField(
            queryset=group_queryset,
            required=False,
            initial=self._groups_with_perms,
            widget=group_widget,
        )
        self.fields['groups'].widget.attrs.setdefault('class', 'form-control')

    def __repr__(self):
        return "<%s: %s?%s>" % (
            self.__class__.__name__,
            self.permission.codename,
            urlencode({
                'staff_only': self.staff_only,
                'max_checkboxes': self.max_checkboxes,
            }))

    @cached_property
    def _users_with_perms(self):
        pks = UserObjectPermission.objects.filter(
            permission=self.permission,
            object_pk=self.instance.pk,
            content_type=self.content_type,
        ).values_list('user', flat=True)
        return get_user_model().objects.filter(pk__in=pks)

    @cached_property
    def _groups_with_perms(self):
        pks = GroupObjectPermission.objects.filter(
            permission=self.permission,
            object_pk=self.instance.pk,
            content_type=self.content_type,
        ).values_list('group', flat=True)
        return Group.objects.filter(pk__in=pks)

    def save(self, *args, **kwargs):
        if self.has_changed():
            # work out our before and after state
            users_before = self._users_with_perms
            users_after = self.cleaned_data['users']
            groups_before = self._groups_with_perms
            groups_after = self.cleaned_data['groups']

            # determine who has had their per object permissions rescinded
            rescind_users = set(users_before).difference(users_after)
            rescind_groups = set(groups_before).difference(groups_after)

            # determine who has had their per object permissions rescinded
            grant_users = set(users_after).difference(users_before)
            grant_groups = set(groups_after).difference(groups_before)

            # rescind and grant access
            for rescind in rescind_users.union(rescind_groups):
                remove_perm(self.permission.codename, rescind, self.instance)

            for grant in grant_users.union(grant_groups):
                assign_perm(self.permission.codename, grant, self.instance)

        return super(PermissionForm, self).save(*args, **kwargs)


class PermissionFormSetMixin(object):
    def __init__(self, instance, queryset, *args, **kwargs):
        super(PermissionFormSetMixin, self).__init__(*args, **kwargs)
        self.instance = instance
        self.queryset = queryset

    def total_form_count(self):
        return self.queryset.count()

    def _construct_form(self, i, **kwargs):
        return super(PermissionFormSetMixin, self)._construct_form(
            i, instance=self.instance, permission=self.queryset[i])

    def save(self, *args, **kwargs):
        res = []
        for form in self.forms:
            res.append(form.save())
        return res


def permissionformset_factory(model, staff_only=None, max_checkboxes=None):
    """
    For the specified Model, return a FormSet class which will allow you to
    control which specific users & groups should have the ability to change
    and delete a model instance.

    The resulting FormSet class will need to be instantiated with an instance
    of the appropriate type.

    The default behaviour is to grant permissions to staff users only.
    Specifying staff_only = False will result in a form that lists all users.

    When there is a large number of users a widget other than checkboxes might
    be preferred to allow for type-ahead searches. We use the Select2 jQuery
    plugin on to of a multiple select widget. Specify the integer number of
    users that will trigger the switch between checkboxes and Select2.

    :param model: Model
    :param staff_only: bool
    :param max_checkboxes: int
    :return: FormSet class
    """
    if staff_only is None:
        staff_only = PermissionForm.staff_only

    if max_checkboxes is None:
        max_checkboxes = PermissionForm.max_checkboxes

    meta = type('Meta', (), {'model': model, 'fields': ('id',)})
    form_class = type(
        '%sPermissionForm' % model.__name__,
        (PermissionForm,),
        {
            'Meta': meta,
            'staff_only': staff_only,
            'max_checkboxes': max_checkboxes,
        }
    )
    formset_base = formset_factory(form_class)
    formset_class = type('%sPermissionFormSet' % model.__name__,
                         (PermissionFormSetMixin, formset_base), {})
    return formset_class
