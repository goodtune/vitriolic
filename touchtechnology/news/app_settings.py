from django.conf import settings
from django.utils.functional import cached_property

__all__ = (
    "DETAIL_IMAGE_KWARGS",
    "DETAIL_IMAGE_PROCESSORS",
    "PAGINATE_BY",
    "THUMBNAIL_IMAGE_KWARGS",
    "THUMBNAIL_IMAGE_PROCESSORS",
)

# Default values
DEFAULT_DETAIL_IMAGE_KWARGS = {}
DEFAULT_DETAIL_IMAGE_PROCESSORS = (
    ("pilkit.processors.resize.SmartResize", (320, 240), {}),
)
DEFAULT_THUMBNAIL_IMAGE_KWARGS = {}
DEFAULT_THUMBNAIL_IMAGE_PROCESSORS = (
    ("pilkit.processors.resize.SmartResize", (160, 120), {}),
)


class _LazyNewsSettings:
    """Lazy accessor for news settings that defers config access until needed."""

    @cached_property
    def DETAIL_IMAGE_KWARGS(self):
        try:
            from constance import config
            return config.TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_KWARGS
        except Exception:
            return getattr(settings, "TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_KWARGS", DEFAULT_DETAIL_IMAGE_KWARGS)

    @cached_property
    def DETAIL_IMAGE_PROCESSORS(self):
        try:
            from constance import config
            return config.TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_PROCESSORS
        except Exception:
            return getattr(settings, "TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_PROCESSORS", DEFAULT_DETAIL_IMAGE_PROCESSORS)

    @cached_property
    def PAGINATE_BY(self):
        try:
            from constance import config
            return config.TOUCHTECHNOLOGY_NEWS_PAGINATE_BY
        except Exception:
            return getattr(settings, "TOUCHTECHNOLOGY_NEWS_PAGINATE_BY", 5)

    @cached_property
    def THUMBNAIL_IMAGE_KWARGS(self):
        try:
            from constance import config
            return config.TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_KWARGS
        except Exception:
            return getattr(settings, "TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_KWARGS", DEFAULT_THUMBNAIL_IMAGE_KWARGS)

    @cached_property
    def THUMBNAIL_IMAGE_PROCESSORS(self):
        try:
            from constance import config
            return config.TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_PROCESSORS
        except Exception:
            return getattr(settings, "TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_PROCESSORS", DEFAULT_THUMBNAIL_IMAGE_PROCESSORS)


_settings = _LazyNewsSettings()

# Export as module-level "constants" (actually properties)
DETAIL_IMAGE_KWARGS = _settings.DETAIL_IMAGE_KWARGS
DETAIL_IMAGE_PROCESSORS = _settings.DETAIL_IMAGE_PROCESSORS
PAGINATE_BY = _settings.PAGINATE_BY
THUMBNAIL_IMAGE_KWARGS = _settings.THUMBNAIL_IMAGE_KWARGS
THUMBNAIL_IMAGE_PROCESSORS = _settings.THUMBNAIL_IMAGE_PROCESSORS

