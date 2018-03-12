from django.conf import settings
from first import first

__all__ = (
    'NODE_CACHE',
    'PAGE_CONTENT_BLOCKS',
    'PAGE_CONTENT_CLASSES',
    'PAGE_TEMPLATE_BASE',
    'PAGE_TEMPLATE_FOLDER',
    'PAGE_TEMPLATE_REGEX',
)

S = lambda n, d=None: getattr(settings, 'TOUCHTECHNOLOGY_' + n, d)

project_template_dirs = first(getattr(settings, 'TEMPLATES', ()), {}).get('DIRS', [])
project_template_base = first(project_template_dirs, 'templates')

NODE_CACHE = getattr(settings, 'TOUCHTECHNOLOGY_NODE_CACHE', 'default')

# These settings allow us to determine where page templates live, which allows
# us not to need to specify each actual template in code.

PAGE_CONTENT_BLOCKS = S('PAGE_CONTENT_BLOCKS', 1)
PAGE_CONTENT_CLASSES = S('PAGE_CONTENT_CLASSES', ('copy',))
PAGE_TEMPLATE_BASE = S('PAGE_TEMPLATE_BASE', project_template_base)
PAGE_TEMPLATE_FOLDER = S('PAGE_TEMPLATE_FOLDER',
                         'touchtechnology/content/pages/')
PAGE_TEMPLATE_REGEX = S('PAGE_TEMPLATE_REGEX', r'\.html$')

TENANT_MEDIA_PUBLIC = S('TENANT_MEDIA_PUBLIC', True)
