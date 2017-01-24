from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import ugettext_lazy as _
from touchtechnology.common.forms import RedefineModelForm


class ProfileForm(RedefineModelForm):
    def clean_email(self):
        UserModel = get_user_model()
        email = self.cleaned_data.get('email')
        other_users = UserModel.objects.exclude(pk=self.instance.pk)
        if other_users.filter(email__iexact=email):
            raise forms.ValidationError(_("This email address is already in "
                                          "use. Please supply a different "
                                          "email address."))
        return email

    class Meta:
        model = get_user_model()
        fields = (
            'first_name',
            'last_name',
            'email',
        )
        redefine = (
            ('first_name', {'required': True}),
            ('last_name', {'required': True}),
            ('email', {
                'help_text': _("Your email address is also your "
                               "username.<br />Please ensure you "
                               "enter it correctly."),
                'required': True,
            }),
        )
