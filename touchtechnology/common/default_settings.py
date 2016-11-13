from django.conf import settings
from django.utils.module_loading import import_string

__all__ = (
    'APP_ROUTING',
    'AUTH_FORM_CLASS',
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

A = lambda n, d: getattr(settings, 'AUTHENTICATION_' + n, d)
C = lambda n, d: import_string(A(n, d))
S = lambda n, d=None: getattr(settings, 'TOUCHTECHNOLOGY_' + n, d)

APP_ROUTING = S('APP_ROUTING', ())
AUTH_FORM_CLASS = C('FORM_CLASS',
                    'django.contrib.auth.forms.AuthenticationForm')
CURRENCY_ABBREVIATION = S('CURRENCY_ABBREVIATION', 'AUD')
CURRENCY_SYMBOL = S('CURRENCY_SYMBOL', '$')
PAGINATE_BY = S('PAGINATE_BY', 5)
SITEMAP_CACHE_DURATION = S('SITEMAP_DURATION')
SITEMAP_EDIT_PARENT = S('SITEMAP_EDIT_PARENT', False)
SITEMAP_HTTPS_OPTION = S('HTTPS_OPTION', False)
SITEMAP_ROOT = S('SITEMAP_ROOT')
STORAGE_FOLDER = S('STORAGE_FOLDER')
STORAGE_URL = S('STORAGE_URL')
