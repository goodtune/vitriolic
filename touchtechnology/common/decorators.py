import logging

from django.contrib.auth.decorators import (
    login_required, permission_required, user_passes_test,
)
from django.utils.decorators import method_decorator
from django.utils.functional import wraps
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

logger = logging.getLogger(__name__)


@user_passes_test
def staff_login_required(user):
    logger.debug("staff_login_required: %s: %s", user, user.is_staff)
    return user.is_staff


@user_passes_test
def superuser_login_required(user):
    logger.debug("superuser_login_required: %s: %s", user, user.is_superuser)
    return user.is_superuser


def node2extracontext(f, *a, **kw):
    @wraps(f)
    def _decorated(*args, **kwargs):
        node = kwargs.pop("node", None)
        extra_context = kwargs.setdefault("extra_context", {})
        if node is not None:
            extra_context.update({"node": node})
        return f(*args, **kwargs)

    return _decorated


cache_control_m = method_decorator(cache_control)
csrf_exempt_m = method_decorator(csrf_exempt)
login_required_m = method_decorator(login_required)
never_cache_m = method_decorator(never_cache)
permission_required_m = method_decorator(permission_required)
staff_login_required_m = method_decorator(staff_login_required)
superuser_login_required_m = method_decorator(superuser_login_required)
user_passes_test_m = method_decorator(user_passes_test)

require_GET_m = method_decorator(require_GET)
require_POST_m = method_decorator(require_POST)
