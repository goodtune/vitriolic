from django.utils.functional import SimpleLazyObject

__all__ = (
    "DETAIL_IMAGE_KWARGS",
    "DETAIL_IMAGE_PROCESSORS",
    "PAGINATE_BY",
    "THUMBNAIL_IMAGE_KWARGS",
    "THUMBNAIL_IMAGE_PROCESSORS",
)


# Use SimpleLazyObject to delay accessing config until actually needed
def _get_detail_image_kwargs():
    from constance import config
    return config.TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_KWARGS


def _get_detail_image_processors():
    from constance import config
    return config.TOUCHTECHNOLOGY_NEWS_DETAIL_IMAGE_PROCESSORS


def _get_paginate_by():
    from constance import config
    return config.TOUCHTECHNOLOGY_NEWS_PAGINATE_BY


def _get_thumbnail_image_kwargs():
    from constance import config
    return config.TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_KWARGS


def _get_thumbnail_image_processors():
    from constance import config
    return config.TOUCHTECHNOLOGY_NEWS_THUMBNAIL_IMAGE_PROCESSORS


DETAIL_IMAGE_KWARGS = SimpleLazyObject(_get_detail_image_kwargs)
DETAIL_IMAGE_PROCESSORS = SimpleLazyObject(_get_detail_image_processors)
PAGINATE_BY = SimpleLazyObject(_get_paginate_by)
THUMBNAIL_IMAGE_KWARGS = SimpleLazyObject(_get_thumbnail_image_kwargs)
THUMBNAIL_IMAGE_PROCESSORS = SimpleLazyObject(_get_thumbnail_image_processors)

