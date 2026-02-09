import os
import socket

from django.utils import timezone

from touchtechnology.common.default_settings import HTMX_ADMIN_TABS
from touchtechnology.common.forms.tz import SelectTimezoneForm


def env(request):
    return {"SITE_ENV": os.environ.get("SITE_ENV", "dev")}


def query_string(request):
    return {"QUERY_STRING": request.META.get("QUERY_STRING")}


def site(request):
    return {"hostname": socket.gethostname()}


def tz(request):
    return {
        "select_timezone_form": SelectTimezoneForm(),
        "TIME_ZONE": timezone.get_current_timezone_name(),
    }


def htmx_admin_tabs(request):
    return {"htmx_admin_tabs": HTMX_ADMIN_TABS}
