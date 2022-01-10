from django.forms import widgets
from django.utils.encoding import smart_str
from django.utils.translation import gettext_lazy as _


class BootstrapFormControlMixin(object):
    """
    Twitter bootstrap is the most widely used user-interface framework. Many
    designers will have experience with it, and there are numerous off-shelf
    themes being built for marketplaces that leverage bootstrap.

    This mixin should be applied to all forms. It will add placeholder text and
    set the bootstrap "form-control" class to the widget of the field.
    """

    def __init__(self, *args, **kwargs):
        super(BootstrapFormControlMixin, self).__init__(*args, **kwargs)
        for field_name in getattr(self, "fields", ()):
            field = self.fields[field_name]

            # Which widget types don't we want to have the placeholder
            # overloaded with the title?
            if not isinstance(field.widget, (widgets.RadioSelect, widgets.MultiWidget)):
                field.widget.attrs.setdefault("placeholder", field.label)

            # Which widget types don't we want to have the class attribute set
            # to be 'form-control'?
            if not isinstance(field.widget, (widgets.RadioSelect,)):
                field.widget.attrs["class"] = "form-control"


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
            self.fields.pop("slug", None)
            self.fields.pop("slug_locked", None)
        else:
            self.fields["slug"].required = False
            self.fields["slug"].help_text = _(
                "If left blank, this will "
                "be automatically set based "
                "on the title."
            )


class LabelFromInstanceMixin(object):
    def __init__(self, label_from_instance="name", *args, **kwargs):
        super(LabelFromInstanceMixin, self).__init__(*args, **kwargs)
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


class PermissionFormSetMixin(object):
    def __init__(self, instance, queryset, *args, **kwargs):
        super(PermissionFormSetMixin, self).__init__(*args, **kwargs)
        self.instance = instance
        self.queryset = queryset

    def total_form_count(self):
        return self.queryset.count()

    def _construct_form(self, i, **kwargs):
        return super(PermissionFormSetMixin, self)._construct_form(
            i, instance=self.instance, permission=self.queryset[i]
        )

    def save(self, *args, **kwargs):
        res = []
        for form in self.forms:
            res.append(form.save())
        return res
