import logging
import os.path
from importlib import import_module

from django.conf import settings
from django.core.cache import cache
from django.db.models.signals import post_save
from django.db.utils import DatabaseError
from django.utils.module_loading import import_string
from touchtechnology.common.models import SitemapNode
from touchtechnology.content.app_settings import TENANT_MEDIA_PUBLIC
from touchtechnology.content.models import Placeholder

logger = logging.getLogger(__name__)


def install_placeholder(app):
    application = import_module(app)
    for cls_name in getattr(application, "INSTALL", ()):
        path = "%s.sites.%s" % (app, cls_name)
        logger.debug('Installing application "{0}"'.format(path))
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
                    'Application "%s" (pk=%d) already ' "exists, skipping.",
                    placeholder.path,
                    placeholder.pk,
                )


def template_path(base, filename, *args):
    args = [arg for arg in args if arg]
    for index in range(len(args), 0, -1):
        yield os.path.join(base, os.path.join(*args[:index]), filename)
    yield os.path.join(base, filename)


def get_media_storage(request):
    if hasattr(request, "tenant"):
        from tenant_schemas.utils import get_public_schema_name

        public = request.tenant.schema_name == get_public_schema_name()
        if not public or (public and not TENANT_MEDIA_PUBLIC):
            return os.path.join(settings.MEDIA_ROOT, request.tenant.domain_url)

    return settings.MEDIA_ROOT


def invalidate_sitemapnode_urlpatterns(sender, instance, **kwargs):
    """
    When a SitemapNode is changed, we need to invalidate the cache so that
    subsequent requests have a newly generated urlconf derived.

    We could add extra conditional checking - for example, if the slug or the
    keyword arguments to a Placeholder node have changed. This will be _far_
    less frequent than it would seem worthwhile to worry about.
    """
    logger.debug("SitemapNodeMiddleware cache requires invalidation.")
    middleware = import_module("touchtechnology.content.middleware")
    cache.delete(middleware.DEHYDRATED_URLPATTERNS_KEY)


post_save.connect(invalidate_sitemapnode_urlpatterns, SitemapNode)
