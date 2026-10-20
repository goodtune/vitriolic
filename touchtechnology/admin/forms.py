from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from modelforms.forms import ModelForm

from touchtechnology.common.forms.mixins import BootstrapFormControlMixin, UserMixin

UserModel = get_user_model()


class AdminFormControlMixin(BootstrapFormControlMixin):
    """
    The admin's own form base.

    Forms the admin builds dynamically derive from this rather than from the
    public site's mixin, so the admin can change how its forms behave without
    changing the public forms. The public mixin dresses every widget for
    another theme (a class, and a placeholder that repeats the label); the
    console labels its fields and styles controls by type, so both are taken
    off again here.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in getattr(self, "fields", {}).values():
            attrs = field.widget.attrs
            if attrs.get("class") == "form-control":
                del attrs["class"]
            if attrs.get("placeholder") == field.label:
                del attrs["placeholder"]


class UserEditForm(UserMixin, ModelForm):
    class Meta:
        model = UserModel
        fields = "__all__"
        help_texts = {
            "is_active": _("A disabled account cannot be used to login to the site."),
            "is_staff": _(
                "Content editor's have access to this administration interface."
            ),
            "is_superuser": _("Should this user be all knowing and all powerful?"),
        }
        labels = {
            "is_active": _("Enabled"),
            "is_staff": _("Content editor"),
            "is_superuser": _("God mode"),
        }


class GroupEditForm(UserMixin, ModelForm):
    def __init__(self, *args, **kwargs):
        super(GroupEditForm, self).__init__(*args, **kwargs)
        # The django.contrib applications don't benefit from the
        # touchtechnology.common database fields, so we need to tweak this
        # field queryset the old fashioned way to make sure we're doing a join.
        self.fields["permissions"].queryset = self.fields[
            "permissions"
        ].queryset.select_related()

    class Meta:
        model = Group
        fields = (
            "name",
            "permissions",
        )
        help_texts = {
            "permissions": _("Members of this group will have " "these permissions."),
        }
