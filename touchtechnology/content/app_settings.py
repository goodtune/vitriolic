from constance import config
from django.conf import settings
from first import first

__all__ = (
    "NODE_CACHE",
    "PAGE_CONTENT_BLOCKS",
    "PAGE_CONTENT_CLASSES",
    "PAGE_TEMPLATE_BASE",
    "PAGE_TEMPLATE_FOLDER",
    "PAGE_TEMPLATE_REGEX",
)

# Get project template dirs for fallback if not configured in constance
project_template_dirs = first(getattr(settings, "TEMPLATES", ()), {}).get("DIRS", [])
project_template_base = first(project_template_dirs, "templates")

NODE_CACHE = config.TOUCHTECHNOLOGY_NODE_CACHE

# These settings allow us to determine where page templates live, which allows
# us not to need to specify each actual template in code.

PAGE_CONTENT_BLOCKS = config.TOUCHTECHNOLOGY_PAGE_CONTENT_BLOCKS
PAGE_CONTENT_CLASSES = config.TOUCHTECHNOLOGY_PAGE_CONTENT_CLASSES
PAGE_TEMPLATE_BASE = config.TOUCHTECHNOLOGY_PAGE_TEMPLATE_BASE or project_template_base
PAGE_TEMPLATE_FOLDER = config.TOUCHTECHNOLOGY_PAGE_TEMPLATE_FOLDER
PAGE_TEMPLATE_REGEX = config.TOUCHTECHNOLOGY_PAGE_TEMPLATE_REGEX

TENANT_MEDIA_PUBLIC = config.TOUCHTECHNOLOGY_TENANT_MEDIA_PUBLIC
