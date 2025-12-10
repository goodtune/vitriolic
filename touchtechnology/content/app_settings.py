from django.conf import settings
from django.utils.functional import SimpleLazyObject
from first import first

__all__ = (
    "NODE_CACHE",
    "PAGE_CONTENT_BLOCKS",
    "PAGE_CONTENT_CLASSES",
    "PAGE_TEMPLATE_BASE",
    "PAGE_TEMPLATE_FOLDER",
    "PAGE_TEMPLATE_REGEX",
)


# Use SimpleLazyObject to delay accessing config until actually needed
def _get_node_cache():
    from constance import config
    return config.TOUCHTECHNOLOGY_NODE_CACHE


def _get_page_content_blocks():
    from constance import config
    return config.TOUCHTECHNOLOGY_PAGE_CONTENT_BLOCKS


def _get_page_content_classes():
    from constance import config
    return config.TOUCHTECHNOLOGY_PAGE_CONTENT_CLASSES


def _get_page_template_base():
    from constance import config
    # Get project template dirs for fallback if not configured in constance
    project_template_dirs = first(getattr(settings, "TEMPLATES", ()), {}).get("DIRS", [])
    project_template_base = first(project_template_dirs, "templates")
    return config.TOUCHTECHNOLOGY_PAGE_TEMPLATE_BASE or project_template_base


def _get_page_template_folder():
    from constance import config
    return config.TOUCHTECHNOLOGY_PAGE_TEMPLATE_FOLDER


def _get_page_template_regex():
    from constance import config
    return config.TOUCHTECHNOLOGY_PAGE_TEMPLATE_REGEX


def _get_tenant_media_public():
    from constance import config
    return config.TOUCHTECHNOLOGY_TENANT_MEDIA_PUBLIC


NODE_CACHE = SimpleLazyObject(_get_node_cache)
PAGE_CONTENT_BLOCKS = SimpleLazyObject(_get_page_content_blocks)
PAGE_CONTENT_CLASSES = SimpleLazyObject(_get_page_content_classes)
PAGE_TEMPLATE_BASE = SimpleLazyObject(_get_page_template_base)
PAGE_TEMPLATE_FOLDER = SimpleLazyObject(_get_page_template_folder)
PAGE_TEMPLATE_REGEX = SimpleLazyObject(_get_page_template_regex)
TENANT_MEDIA_PUBLIC = SimpleLazyObject(_get_tenant_media_public)

