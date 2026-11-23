from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from guardian.shortcuts import get_objects_for_user

from tournamentcontrol.competition.models import Season

STREAM = "competition.stream_season"
COMMENTATE = "competition.commentate_season"
SCORE = "competition.score_season"
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


# The global permission is checked first: Django caches it on the user, while
# every object check is a guardian query, once per row on the results panel.


def can_stream(user, season):
    return user.has_perm(STREAM) or user.has_perm(STREAM, season)


def can_commentate(user, season):
    """
    May watch the season's booths: the lamp, the strip and the panes about
    every match of the season. Whoever may run the broadcast may watch it.
    """
    return (
        user.has_perm(COMMENTATE)
        or user.has_perm(COMMENTATE, season)
        or can_stream(user, season)
    )


def can_score(user, season):
    """May keep the season's scoreboards: change a score and start a clock."""
    return user.has_perm(SCORE) or user.has_perm(SCORE, season)


def booth_seasons(user):
    """The seasons whose booths ``user`` may open: see ``can_commentate``."""
    return get_objects_for_user(user, [COMMENTATE, STREAM], Season, any_perm=True)


def can_change_match(user, match):
    return user.has_perm(CHANGE_MATCH) or user.has_perm(CHANGE_MATCH, match)


def can_enter_statistics(user):
    return all(user.has_perm(perm) for perm in STATISTICS)


def require(condition):
    if not condition:
        raise PermissionDenied
