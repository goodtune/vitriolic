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
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_NODE_CACHE
    except Exception:
        # Fallback to Django settings during migrations or if constance not ready
        return getattr(settings, "TOUCHTECHNOLOGY_NODE_CACHE", "default")


def _get_page_content_blocks():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_PAGE_CONTENT_BLOCKS
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_PAGE_CONTENT_BLOCKS", 1)


def _get_page_content_classes():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_PAGE_CONTENT_CLASSES
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_PAGE_CONTENT_CLASSES", ("copy",))


def _get_page_template_base():
    try:
        from constance import config
        value = config.TOUCHTECHNOLOGY_PAGE_TEMPLATE_BASE
        if value:
            return value
    except Exception:
        pass
    # Get project template dirs for fallback if not configured in constance
    project_template_dirs = first(getattr(settings, "TEMPLATES", ()), {}).get("DIRS", [])
    project_template_base = first(project_template_dirs, "templates")
    return getattr(settings, "TOUCHTECHNOLOGY_PAGE_TEMPLATE_BASE", None) or project_template_base


def _get_page_template_folder():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_PAGE_TEMPLATE_FOLDER
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_PAGE_TEMPLATE_FOLDER", "touchtechnology/content/pages/")


def _get_page_template_regex():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_PAGE_TEMPLATE_REGEX
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_PAGE_TEMPLATE_REGEX", r"\.html$")


def _get_tenant_media_public():
    try:
        from constance import config
        return config.TOUCHTECHNOLOGY_TENANT_MEDIA_PUBLIC
    except Exception:
        return getattr(settings, "TOUCHTECHNOLOGY_TENANT_MEDIA_PUBLIC", True)


NODE_CACHE = SimpleLazyObject(_get_node_cache)
PAGE_CONTENT_BLOCKS = SimpleLazyObject(_get_page_content_blocks)
PAGE_CONTENT_CLASSES = SimpleLazyObject(_get_page_content_classes)
PAGE_TEMPLATE_BASE = SimpleLazyObject(_get_page_template_base)
PAGE_TEMPLATE_FOLDER = SimpleLazyObject(_get_page_template_folder)
PAGE_TEMPLATE_REGEX = SimpleLazyObject(_get_page_template_regex)
TENANT_MEDIA_PUBLIC = SimpleLazyObject(_get_tenant_media_public)

