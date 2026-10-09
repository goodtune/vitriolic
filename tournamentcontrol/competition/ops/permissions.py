from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

STREAM = "competition.stream_season"
CHANGE_MATCH = "competition.change_match"
STATISTICS = (
    "competition.add_simplescorematchstatistic",
    "competition.change_simplescorematchstatistic",
)


def staff_required(view):
    @wraps(view)
    def wrapper(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_staff:
            raise PermissionDenied
        return view(self, request, *args, **kwargs)

    return wrapper


def can_stream(user, season):
    return user.has_perm(STREAM, season) or user.has_perm(STREAM)


def can_change_match(user, match):
    return user.has_perm(CHANGE_MATCH, match) or user.has_perm(CHANGE_MATCH)


def can_enter_statistics(user):
    return all(user.has_perm(perm) for perm in STATISTICS)


def require(condition):
    if not condition:
        raise PermissionDenied
