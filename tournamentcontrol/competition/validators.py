from django.core import validators
from django.utils.translation import gettext_lazy as _

validate_hashtag = validators.RegexValidator(
    r"^(?:#)(\w+)$",
    _("Enter a valid value. Make sure you include the # symbol."),
)
