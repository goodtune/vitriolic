from django.conf import settings
from django.utils.functional import SimpleLazyObject, empty

__all__ = (
    "APP_ROUTING",
    "CURRENCY_ABBREVIATION",
    "CURRENCY_SYMBOL",
    "HTMX_ADMIN_TABS",
    "PAGINATE_BY",
    "SITEMAP_CACHE_DURATION",
    "SITEMAP_EDIT_PARENT",
    "SITEMAP_HTTPS_OPTION",
    "SITEMAP_ROOT",
    "STORAGE_FOLDER",
    "STORAGE_URL",
)


class LazySetting(SimpleLazyObject):
    """SimpleLazyObject extended with numeric coercion for settings values."""

    def __int__(self):
        if self._wrapped is empty:
            self._setup()
        return int(self._wrapped)

    def __float__(self):
        if self._wrapped is empty:
            self._setup()
        return float(self._wrapped)


def A(n, d):
    return LazySetting(lambda: getattr(settings, "AUTHENTICATION_" + n, d))


def S(n, d=None):
    return LazySetting(lambda: getattr(settings, "TOUCHTECHNOLOGY_" + n, d))


APP_ROUTING = S("APP_ROUTING", ())
HTMX_ADMIN_TABS = S("HTMX_ADMIN_TABS", False)
CURRENCY_ABBREVIATION = S("CURRENCY_ABBREVIATION", "AUD")
CURRENCY_SYMBOL = S("CURRENCY_SYMBOL", "$")
PAGINATE_BY = S("PAGINATE_BY", 5)
PROFILE_FORM_CLASS = S(
    "PROFILE_FORM_CLASS", "touchtechnology.common.forms_lazy.ProfileForm"
)
SITEMAP_CACHE_DURATION = S("SITEMAP_DURATION")
SITEMAP_EDIT_PARENT = S("SITEMAP_EDIT_PARENT", False)
SITEMAP_HTTPS_OPTION = S("HTTPS_OPTION", False)
SITEMAP_ROOT = S("SITEMAP_ROOT")
STORAGE_FOLDER = S("STORAGE_FOLDER")
STORAGE_URL = S("STORAGE_URL")
