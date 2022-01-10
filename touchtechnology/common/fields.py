from django import forms
from django.utils.translation import gettext_lazy as _


def boolean_coerce(value):
    if value in {1, "1"}:
        return True
    if value in {0, "0"}:
        return False


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
        super(BooleanChoiceField, self).__init__(*args, **defaults)

    def prepare_value(self, value):
        if value is not None:
            return str(int(value))
