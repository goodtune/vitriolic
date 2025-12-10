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
# This avoids database access during module import
def _get_app_routing():
    from constance import config
    return config.TOUCHTECHNOLOGY_APP_ROUTING


def _get_currency_abbreviation():
    from constance import config
    return config.TOUCHTECHNOLOGY_CURRENCY_ABBREVIATION


def _get_currency_symbol():
    from constance import config
    return config.TOUCHTECHNOLOGY_CURRENCY_SYMBOL


def _get_paginate_by():
    from constance import config
    return config.TOUCHTECHNOLOGY_PAGINATE_BY


def _get_profile_form_class():
    from constance import config
    return config.TOUCHTECHNOLOGY_PROFILE_FORM_CLASS


def _get_sitemap_cache_duration():
    from constance import config
    return config.TOUCHTECHNOLOGY_SITEMAP_CACHE_DURATION


def _get_sitemap_edit_parent():
    from constance import config
    return config.TOUCHTECHNOLOGY_SITEMAP_EDIT_PARENT


def _get_sitemap_https_option():
    from constance import config
    return config.TOUCHTECHNOLOGY_SITEMAP_HTTPS_OPTION


def _get_sitemap_root():
    from constance import config
    return config.TOUCHTECHNOLOGY_SITEMAP_ROOT


def _get_storage_folder():
    from constance import config
    return config.TOUCHTECHNOLOGY_STORAGE_FOLDER


def _get_storage_url():
    from constance import config
    return config.TOUCHTECHNOLOGY_STORAGE_URL


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

