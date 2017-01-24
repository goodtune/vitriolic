import logging
import socket
import sys

import django
import pytz
from django.utils import timezone
from touchtechnology.common.utils import get_timezone_from_request

logger = logging.getLogger(__name__)


class ServedByMiddleware(object):
    """
    Expose in our HTTP response headers a number of useful environment values
    that may be useful during debugging.
    """
    def process_response(self, request, response):
        if 'HTTP_X_DETAIL' in request.META or response.status_code >= 500:
            response['X-Django-Version'] = django.get_version()
            response['X-Python-Version'] = ' '.join(sys.version.split())
            response['X-Pytz-Version'] = pytz.__version__
            response['X-Served-By'] = socket.gethostname()
            response['X-Timezone-Name'] = timezone.get_current_timezone_name()
        return response


class TimezoneMiddleware(object):

    def process_request(self, request):
        tzinfo = get_timezone_from_request(request)
        if tzinfo is not None:
            logger.debug(
                'Activating user timezone "%s" for this request.', tzinfo)
            request.tzinfo = tzinfo
            timezone.activate(tzinfo)

    def process_response(self, request, response):
        if hasattr(request, 'tzinfo'):
            logger.debug(
                'Forcibly reset the timezone from "%s" back to "%s".',
                request.tzinfo, timezone.get_default_timezone_name())
            timezone.deactivate()
        return response
