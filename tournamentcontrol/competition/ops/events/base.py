"""
The interface every ops event bus backend implements.
"""

import abc


class Backend(abc.ABC):
    """
    An event bus for one deployment. ``publish`` and ``recent`` are called
    from sync code; ``subscribe`` is consumed by the async SSE views.

    The class named by ``OPS_EVENTS_BACKEND`` is instantiated once per
    process with the keyword arguments in ``OPS_EVENTS_OPTIONS``.
    """

    @abc.abstractmethod
    def publish(self, season_id, event):
        """
        Deliver ``event`` (a JSON-serialisable dict) to every subscriber of
        ``season_id`` and remember it for ``recent``.
        """

    @abc.abstractmethod
    async def subscribe(self, season_id, idle):
        """
        An async generator. Yield ``None`` once as soon as the subscription
        is registered, then an event dict per event, or ``None`` after
        ``idle`` seconds without one. Closing the generator unsubscribes.
        """
        yield None

    @abc.abstractmethod
    def recent(self, season_id):
        """
        Return the most recent events for ``season_id``, newest first, at
        most ``OPS_ACTIVITY_LENGTH`` of them.
        """
