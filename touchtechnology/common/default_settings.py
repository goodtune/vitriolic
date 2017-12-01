from django.conf import settings

__all__ = (
    'APP_ROUTING',
    'CURRENCY_ABBREVIATION',
    'CURRENCY_SYMBOL',
    'PAGINATE_BY',
    'SITEMAP_CACHE_DURATION',
    'SITEMAP_EDIT_PARENT',
    'SITEMAP_HTTPS_OPTION',
    'SITEMAP_ROOT',
    'STORAGE_FOLDER',
    'STORAGE_URL',
)


def A(n, d):
    return getattr(settings, 'AUTHENTICATION_' + n, d)


def S(n, d=None):
    return getattr(settings, 'TOUCHTECHNOLOGY_' + n, d)


APP_ROUTING = S('APP_ROUTING', ())
CURRENCY_ABBREVIATION = S('CURRENCY_ABBREVIATION', 'AUD')
CURRENCY_SYMBOL = S('CURRENCY_SYMBOL', '$')
PAGINATE_BY = S('PAGINATE_BY', 5)
SITEMAP_CACHE_DURATION = S('SITEMAP_DURATION')
SITEMAP_EDIT_PARENT = S('SITEMAP_EDIT_PARENT', False)
SITEMAP_HTTPS_OPTION = S('HTTPS_OPTION', False)
SITEMAP_ROOT = S('SITEMAP_ROOT')
STORAGE_FOLDER = S('STORAGE_FOLDER')
STORAGE_URL = S('STORAGE_URL')
