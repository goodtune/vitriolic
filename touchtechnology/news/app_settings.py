from django.utils.functional import cached_property

__all__ = (
    "DETAIL_IMAGE_KWARGS",
    "DETAIL_IMAGE_PROCESSORS",
    "PAGINATE_BY",
    "THUMBNAIL_IMAGE_KWARGS",
    "THUMBNAIL_IMAGE_PROCESSORS",
)


class _LazyNewsSettings:
    """Lazy accessor for news settings that defers config access until needed."""

    @cached_property
    def DETAIL_IMAGE_KWARGS(self):
        from constance import config
        return config.TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_KWARGS

    @cached_property
    def DETAIL_IMAGE_PROCESSORS(self):
        from constance import config
        return config.TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_PROCESSORS

    @cached_property
    def PAGINATE_BY(self):
        from constance import config
        return config.TOUCHTECHNOLOGY_NEWS_PAGINATE_BY

    @cached_property
    def THUMBNAIL_IMAGE_KWARGS(self):
        from constance import config
        return config.TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_KWARGS

    @cached_property
    def THUMBNAIL_IMAGE_PROCESSORS(self):
        from constance import config
        return config.TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_PROCESSORS


_settings = _LazyNewsSettings()

# Export as module-level "constants" (actually properties)
DETAIL_IMAGE_KWARGS = _settings.DETAIL_IMAGE_KWARGS
DETAIL_IMAGE_PROCESSORS = _settings.DETAIL_IMAGE_PROCESSORS
PAGINATE_BY = _settings.PAGINATE_BY
THUMBNAIL_IMAGE_KWARGS = _settings.THUMBNAIL_IMAGE_KWARGS
THUMBNAIL_IMAGE_PROCESSORS = _settings.THUMBNAIL_IMAGE_PROCESSORS

