from touchtechnology.common.default_settings import lazy_setting

__all__ = (
    "ACTIVITY_LENGTH",
    "EVENTS_BACKEND",
    "EVENTS_KEEPALIVE",
    "EVENTS_OPTIONS",
)


def S(n, d):
    return lazy_setting("COMPOPS_" + n, d)


EVENTS_BACKEND = S(
    "EVENTS_BACKEND",
    "tournamentcontrol.competition.compops.events.memory.MemoryBackend",
)
EVENTS_OPTIONS = S("EVENTS_OPTIONS", {})
EVENTS_KEEPALIVE = S("EVENTS_KEEPALIVE", 20)
ACTIVITY_LENGTH = S("ACTIVITY_LENGTH", 50)
