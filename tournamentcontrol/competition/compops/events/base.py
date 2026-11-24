"""
The interface every ops event bus backend implements.
"""

import abc


class Backend(abc.ABC):
    """
    An event bus for one deployment. ``publish`` and ``recent`` are called
    from sync code; ``subscribe`` is consumed by the async SSE views.

    The class named by ``COMPOPS_EVENTS_BACKEND`` is instantiated once per
    process with the keyword arguments in ``COMPOPS_EVENTS_OPTIONS``.

    Each method takes a ``channel``, a string that names one season of one
    tenant (see ``events.channel``). The backend keeps channels apart and
    reads nothing more into them.
    """

    @abc.abstractmethod
    def publish(self, channel, event):
        """
        Deliver ``event`` (a JSON-serialisable dict) to every subscriber of
        ``channel`` and remember it for ``recent``.
        """

    @abc.abstractmethod
    async def subscribe(self, channel, idle):
        """
        An async generator. Yield ``None`` once as soon as the subscription
        is registered, then an event dict per event, or ``None`` after
        ``idle`` seconds without one. Closing the generator unsubscribes.
        """
        yield None

    @abc.abstractmethod
    def recent(self, channel):
        """
        Return the most recent events for ``channel``, newest first, at
        most ``COMPOPS_ACTIVITY_LENGTH`` of them.
        """
