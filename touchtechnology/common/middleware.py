import logging
import socket
import sys

import django
import pytz
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from touchtechnology.common.utils import get_timezone_from_request

logger = logging.getLogger(__name__)


class AcceptsMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.accepts = set(request.META.get("HTTP_ACCEPT", "").split(","))


def served_by_middleware(get_response):
    """
    Expose in our HTTP response headers a number of useful environment values
    that may be useful during debugging.
    """
    def middleware(request):
        response = get_response(request)
        if 'HTTP_X_DETAIL' in request.META or response.status_code >= 500:
            response['X-Django-Version'] = django.get_version()
            response['X-Python-Version'] = ' '.join(sys.version.split())
            response['X-Pytz-Version'] = pytz.__version__
            response['X-Served-By'] = socket.gethostname()
            response['X-Timezone-Name'] = timezone.get_current_timezone_name()
        return response
    return middleware


def timezone_middleware(get_response):
    """
    Activate the timezone for this request/response cycle if
    get_timezone_from_request returns a tzinfo.
    """
    def middleware(request):
        tzinfo = get_timezone_from_request(request)

        if tzinfo is not None:
            logger.debug(
                'Activating user timezone "%s" for this request.', tzinfo)
            request.tzinfo = tzinfo
            timezone.activate(tzinfo)

        response = get_response(request)

        if tzinfo is not None:
            logger.debug(
                'Forcibly reset the timezone from "%s" back to "%s".',
                request.tzinfo, timezone.get_default_timezone_name())
            timezone.deactivate()

        return response
    return middleware
