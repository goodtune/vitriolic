"""[Developer API] Helper utilities for content management."""

import logging
import os.path
from importlib import import_module

from django.conf import settings
from django.core.cache import cache
from django.db import DEFAULT_DB_ALIAS
from django.db.models.signals import post_delete, post_save
from django.db.utils import DatabaseError
from django.utils.module_loading import import_string

from touchtechnology.common.models import SitemapNode
from touchtechnology.common.utils import get_schema_name
from touchtechnology.content.app_settings import TENANT_MEDIA_PUBLIC
from touchtechnology.content.models import Placeholder

# SitemapNodeMiddleware caches the URL tree it builds from the sitemap.
DEHYDRATED_URLPATTERNS_KEY = "urlpatterns"
DEHYDRATED_URLPATTERNS_TIMEOUT = 600

logger = logging.getLogger(__name__)


def install_placeholder(app):
    """Create placeholder records for a given application."""
    application = import_module(app)
    for cls_name in getattr(application, "INSTALL", ()):
        path = f"{app}.sites.{cls_name}"
        logger.debug('Installing application "%s"', path)
        site = import_string(path)()
        namespace = site.app_name
        try:
            placeholder, created = Placeholder.objects.get_or_create(
                path=path, namespace=namespace
            )
        except DatabaseError:
            logger.exception("Unable to install placeholder: %s", path)
        else:
            if created:
                logger.info(
                    'Registered new application "%s" (pk=%d)',
                    placeholder.path,
                    placeholder.pk,
                )
            else:
                logger.debug(
                    'Application "%s" (pk=%d) already exists, skipping.',
                    placeholder.path,
                    placeholder.pk,
                )


def template_path(base, filename, *args):
    """Yield template paths from most specific to fallback."""
    args = [arg for arg in args if arg]
    for index in range(len(args), 0, -1):
        yield os.path.join(base, os.path.join(*args[:index]), filename)
    yield os.path.join(base, filename)


def get_media_storage(request):
    """Return the media storage path for the current tenant."""
    if hasattr(request, "tenant"):
        get_public_schema_name = import_string(
            "tenant_schemas.utils.get_public_schema_name"
        )

        public = request.tenant.schema_name == get_public_schema_name()
        if not public or (public and not TENANT_MEDIA_PUBLIC):
            return os.path.join(settings.MEDIA_ROOT, request.tenant.domain_url)

    return settings.MEDIA_ROOT


def urlpatterns_cache_version(using=DEFAULT_DB_ALIAS):
    """
    Return the cache version of the URL tree of the current tenant.

    Each tenant of a ``django-tenant-schemas`` site has its own sitemap, so
    its tree is cached under the name of the schema the connection points at:
    the tenant of the request, or of ``tenant_context`` outside one. That is
    also the schema a node is saved to, so a save throws away the tree of the
    tenant it changed. A single-tenant site uses the cache's default version.
    """
    return get_schema_name(using)


def invalidate_sitemapnode_urlpatterns(
    sender, instance, using=DEFAULT_DB_ALIAS, **kwargs
):
    """
    When a SitemapNode is changed or deleted, we need to invalidate the cache
    so that subsequent requests have a newly generated urlconf derived.

    We could add extra conditional checking - for example, if the slug or the
    keyword arguments to a Placeholder node have changed. This will be _far_
    less frequent than it would seem worthwhile to worry about.

    ``using`` has a default because ``SitemapNode._move`` sends ``post_save``
    itself, without it.
    """
    logger.debug("SitemapNodeMiddleware cache requires invalidation.")
    cache.delete(DEHYDRATED_URLPATTERNS_KEY, version=urlpatterns_cache_version(using))


post_save.connect(invalidate_sitemapnode_urlpatterns, SitemapNode)
post_delete.connect(invalidate_sitemapnode_urlpatterns, SitemapNode)
