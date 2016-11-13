import logging

logger = logging.getLogger(__name__)


def strict_show_toolbar_callback(request):
    """
    Additional check against custom permission ``debug_toolbar.show``.

    :param request: HttpRequest
    :return: bool
    """
    if hasattr(request, 'user') and \
       request.user.has_perm('debug_toolbar.show'):

        logger.debug('DjDT allowed for "%s" <%s>',
                     request.user.get_full_name(),
                     request.user.email)

        return show_toolbar_callback(request)

    return False


def show_toolbar_callback(request):
    """
    For each request, the callback will be invoked to determine if the
    machinery of the django-debug-toolbar should be invoked.

    In consideration of performance, this should be entirely stateless and
    depend on information available in the request only.

    We allow two ways that a user can enable this.

    1. User-Agent spoofing

    Setting the user agent header to include the string "DjangoDebugToolbar"
    will enable the toolbar for that request.

    2. X-DJDT-SHOW header

    Adding a custom header and setting the value to one of "1", "true", "on",
    or "yes" (all case insensitive) will enable the toolbar for that request.

    NOTE: previously this depended on a custom permission, we've relaxed this
    because sometimes it is necessary to debug a live application as an
    unauthenticated user.

    For the old behaviour, use the ``strict_show_toolbar_callback`` instead.

    :param request: HttpRequest
    :return: bool
    """
    ua = request.META.get('HTTP_USER_AGENT', '')
    if ua.find('DjangoDebugToolbar') >= 0:
        logger.info('Enable DjDT by User-Agent "%s"', ua)
        return True

    show = request.META.get('HTTP_X_DJDT_SHOW')
    if show is not None:
        show = show.lower()
        logger.debug('HTTP_X_DJDT_SHOW: %s', show)
    if show in ('1', 'true', 'on', 'yes'):
        logger.info('Enable DjDT by X-DjDT-SHOW header "%s"', show)
        return True

    return False
