from touchtechnology.common.default_settings import lazy_setting

__all__ = (
    "ACTIVITY_LENGTH",
    "EVENTS_BACKEND",
    "EVENTS_KEEPALIVE",
    "EVENTS_OPTIONS",
)


def O(n, d):
    return lazy_setting("OPS_" + n, d)


EVENTS_BACKEND = O(
    "EVENTS_BACKEND", "tournamentcontrol.competition.ops.events.memory.MemoryBackend"
)
EVENTS_OPTIONS = O("EVENTS_OPTIONS", {})
EVENTS_KEEPALIVE = O("EVENTS_KEEPALIVE", 20)
ACTIVITY_LENGTH = O("ACTIVITY_LENGTH", 50)
