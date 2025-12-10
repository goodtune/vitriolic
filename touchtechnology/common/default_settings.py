from django.conf import settings
from django.utils.functional import SimpleLazyObject

__all__ = (
    "APP_ROUTING",
    "CURRENCY_ABBREVIATION",
    "CURRENCY_SYMBOL",
    "PAGINATE_BY",
    "SITEMAP_CACHE_DURATION",
    "SITEMAP_EDIT_PARENT",
    "SITEMAP_HTTPS_OPTION",
    "SITEMAP_ROOT",
    "STORAGE_FOLDER",
    "STORAGE_URL",
)


# Use SimpleLazyObject to delay accessing config until actually needed
# Fall back to Django settings if constance not ready
def _get_app_routing():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_APP_ROUTING
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_APP_ROUTING", ())


def _get_currency_abbreviation():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_CURRENCY_ABBREVIATION
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_CURRENCY_ABBREVIATION", "AUD")


def _get_currency_symbol():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_CURRENCY_SYMBOL
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_CURRENCY_SYMBOL", "$")


def _get_paginate_by():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_PAGINATE_BY
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_PAGINATE_BY", 5)


def _get_profile_form_class():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_PROFILE_FORM_CLASS
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_PROFILE_FORM_CLASS", "touchtechnology.common.forms_lazy.ProfileForm")


def _get_sitemap_cache_duration():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_SITEMAP_CACHE_DURATION
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_SITEMAP_CACHE_DURATION", None)


def _get_sitemap_edit_parent():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_SITEMAP_EDIT_PARENT
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_SITEMAP_EDIT_PARENT", False)


def _get_sitemap_https_option():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_SITEMAP_HTTPS_OPTION
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_SITEMAP_HTTPS_OPTION", False)


def _get_sitemap_root():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_SITEMAP_ROOT
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_SITEMAP_ROOT", None)


def _get_storage_folder():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_STORAGE_FOLDER
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_STORAGE_FOLDER", None)


def _get_storage_url():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_STORAGE_URL
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_STORAGE_URL", None)


APP_ROUTING = SimpleLazyObject(_get_app_routing)
CURRENCY_ABBREVIATION = SimpleLazyObject(_get_currency_abbreviation)
CURRENCY_SYMBOL = SimpleLazyObject(_get_currency_symbol)
PAGINATE_BY = SimpleLazyObject(_get_paginate_by)
PROFILE_FORM_CLASS = SimpleLazyObject(_get_profile_form_class)
SITEMAP_CACHE_DURATION = SimpleLazyObject(_get_sitemap_cache_duration)
SITEMAP_EDIT_PARENT = SimpleLazyObject(_get_sitemap_edit_parent)
SITEMAP_HTTPS_OPTION = SimpleLazyObject(_get_sitemap_https_option)
SITEMAP_ROOT = SimpleLazyObject(_get_sitemap_root)
STORAGE_FOLDER = SimpleLazyObject(_get_storage_folder)
STORAGE_URL = SimpleLazyObject(_get_storage_url)

