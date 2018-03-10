import logging
from calendar import timegm

from django.conf import settings
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.utils.http import http_date, parse_http_date_safe
from django.views.decorators.cache import patch_cache_control
from django.views.decorators.http import last_modified
from touchtechnology.common.models import SitemapNode
from touchtechnology.content.models import Page
from touchtechnology.content.utils import template_path

logger = logging.getLogger(__name__)


def page_last_modified(request, page_id=None, **kwargs):
    last_modified = SitemapNode.objects.aggregate(
        last_modified=Max('last_modified'))['last_modified']
    logger.debug('SitemapNode.last_modified.max="%s"',
                 http_date(timegm(last_modified.utctimetuple())))
    return last_modified


@last_modified(page_last_modified)
def dispatch(request, page_id=None, node=None, url=None):
    if page_id is not None:
        page = get_object_or_404(Page, pk=page_id)
    else:
        page = None

    if page and settings.DEBUG:
        if_modified_since = request.META.get("HTTP_IF_MODIFIED_SINCE")
        if if_modified_since:
            if_modified_since = parse_http_date_safe(if_modified_since)
            res_last_modified = timegm(page.last_modified.utctimetuple())
            logger.debug('page="%d", if-last-modified="%s", '
                         'last-modified="%s"', page_id,
                         http_date(if_modified_since),
                         http_date(res_last_modified))

    base = 'touchtechnology/content'
    args = url.split('/')
    templates = list(template_path(
        base, '%s.html' % (page and 'page' or 'folder'), *args))

    if page and page.template:
        templates.insert(0, page.template)

    context = {
        'page': page,
        'node': node,
    }
    response = TemplateResponse(request, templates, context)

    # For authenticated visitors we may alter the rendered content, so mark
    # the content as private to stop interim caches from keeping a copy.
    if request.user.is_authenticated:
        patch_cache_control(response, private=True)
    return response
