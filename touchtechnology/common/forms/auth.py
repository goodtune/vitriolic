from typing import Optional

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet
from django.forms import BaseFormSet, formset_factory
from django.utils.functional import cached_property
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _
from guardian.models import GroupObjectPermission, UserObjectPermission
from guardian.shortcuts import assign_perm, remove_perm
from modelforms.forms import ModelForm

from touchtechnology.common.forms.fields import (
    EmailField,
    ModelMultipleChoiceField,
)
from touchtechnology.common.forms.mixins import (
    BootstrapFormControlMixin,
    PermissionFormSetMixin,
)


class EmailAuthenticationForm(BootstrapFormControlMixin, AuthenticationForm):
    username = EmailField(label=_("Email Address"))

    def __init__(self, *args, **kwargs):
        super(EmailAuthenticationForm, self).__init__(*args, **kwargs)
        for field_name in self.fields:
            self.fields[field_name].widget.attrs["class"] += " text-center"


class RegistrationForm(forms.Form):
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)
    email = EmailField()
    password1 = forms.CharField(widget=forms.PasswordInput, label=_("Password"))
    password2 = forms.CharField(widget=forms.PasswordInput, label=_("Password (again)"))

    def clean_email(self):
        UserModel = get_user_model()
        email = self.cleaned_data.get("email")
        if UserModel.objects.filter(email__iexact=email):
            raise forms.ValidationError(
                _(
                    "This email address is already in "
                    "use. Please supply a different "
                    "email address."
                )
            )
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError(
                    _("The two password fields " "didn't match.")
                )
        return password2


class PermissionForm(ModelForm):
    """
    Generic form to be used to assign row-level permissions to an object.
    """

    staff_only: bool = True
    max_checkboxes: int = 7  # Set based on number of rows visible in MVP layout

    def __init__(self, permission, *args, **kwargs):
        super(PermissionForm, self).__init__(*args, **kwargs)
        self.content_type = ContentType.objects.get_for_model(self.instance)
        self.permission = permission

        # determine if we should filter to only show staff
        user_queryset = get_user_model().objects.all()
        if self.staff_only:
            user_queryset = user_queryset.filter(is_staff=True)

        group_queryset = Group.objects.all()

        self.fields["users"] = ModelMultipleChoiceField(
            queryset=user_queryset,
            required=False,
            initial=self._users_with_perms,
            label_from_instance=lambda o: o.get_full_name(),
        )
        self.fields["users"].widget.attrs.setdefault("class", "form-control")

        self.fields["groups"] = ModelMultipleChoiceField(
            queryset=group_queryset,
            required=False,
            initial=self._groups_with_perms,
        )
        self.fields["groups"].widget.attrs.setdefault("class", "form-control")

    def __repr__(self):
        return "<%s: %s?%s>" % (
            self.__class__.__name__,
            self.permission.codename,
            urlencode(
                {
                    "staff_only": self.staff_only,
                    "max_checkboxes": self.max_checkboxes,
                }
            ),
        )

    @cached_property
    def _users_with_perms(self):
        pks = UserObjectPermission.objects.filter(
            permission=self.permission,
            object_pk=self.instance.pk,
            content_type=self.content_type,
        ).values_list("user", flat=True)
        return get_user_model().objects.filter(pk__in=pks)

    @cached_property
    def _groups_with_perms(self) -> QuerySet:
        pks = GroupObjectPermission.objects.filter(
            permission=self.permission,
            object_pk=self.instance.pk,
            content_type=self.content_type,
        ).values_list("group", flat=True)
        return Group.objects.filter(pk__in=pks)

    def save(self, *args, **kwargs):
        if self.has_changed():
            # work out our before and after state
            users_before = self._users_with_perms
            users_after = self.cleaned_data["users"]
            groups_before = self._groups_with_perms
            groups_after = self.cleaned_data["groups"]

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


def permissionformset_factory(
    model, staff_only: Optional[bool] = None, max_checkboxes: Optional[int] = None
) -> BaseFormSet:
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

    meta = type("Meta", (), {"model": model, "fields": ("id",)})
    form_class = type(
        "%sPermissionForm" % model.__name__,
        (PermissionForm,),
        {
            "Meta": meta,
            "staff_only": staff_only,
            "max_checkboxes": max_checkboxes,
        },
    )
    formset_base = formset_factory(form_class)
    formset_class = type(
        "%sPermissionFormSet" % model.__name__,
        (PermissionFormSetMixin, formset_base),
        {},
    )
    return formset_class
