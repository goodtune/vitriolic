import logging

from django.template import Library
from touchtechnology.content.models import Chunk

logger = logging.getLogger(__name__)
register = Library()


@register.simple_tag
def chunk(slug):
    instance, created = Chunk.objects.get_or_create(slug=slug)
    if created:
        logger.debug('Created %r' % instance)
    return instance.copy
