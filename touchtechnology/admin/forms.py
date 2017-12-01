from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.forms import BooleanField as BooleanChoiceField
from django.utils.translation import ugettext_lazy as _
from modelforms.forms import ModelForm
from touchtechnology.common.forms.mixins import UserMixin

UserModel = get_user_model()


class UserEditForm(UserMixin, ModelForm):
    is_superuser = BooleanChoiceField(label=_("God mode"),
                                      help_text=_("Should this user be all "
                                                  "knowing and all powerful?"))

    class Meta:
        model = UserModel
        fields = '__all__'  # Django 1.8 requires `fields` to be set
        help_texts = {
            'is_active': _("A disabled account cannot be used to "
                           "login to the site."),
            'is_staff': _("Content editor's have access to this "
                          "administration interface."),
        }
        labels = {
            'is_active': _("Enabled"),
            'is_staff': _("Content editor"),
        }


class GroupEditForm(UserMixin, ModelForm):

    def __init__(self, *args, **kwargs):
        super(GroupEditForm, self).__init__(*args, **kwargs)
        # The django.contrib applications don't benefit from the
        # touchtechnology.common database fields, so we need to tweak this
        # field queryset the old fashioned way to make sure we're doing a join.
        self.fields['permissions'].queryset = \
            self.fields['permissions'].queryset.select_related()

    class Meta:
        model = Group
        fields = (
            'name',
            'permissions',
        )
        help_texts = {
            'permissions': _("Members of this group will have "
                             "these permissions."),
        }
