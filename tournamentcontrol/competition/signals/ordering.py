from tournamentcontrol.competition.signals.decorators import (
    disable_for_loaddata,
)


@disable_for_loaddata
def refresh_order(sender, instance, *args, **kwargs):
    """
    Before a ``Team`` or ``Stage`` is deleted, read its ``order`` again: a
    caller that deletes several rows of a list in turn holds values that the
    earlier deletions have since moved.
    """
    instance.refresh_from_db(fields=["order"])


@disable_for_loaddata
def close_order_gap(sender, instance, *args, **kwargs):
    """
    When a ``Team`` or ``Stage`` has been deleted, move the rows below it in
    its division up one so the list has no gap. Connected to ``post_delete``:
    the row must be gone before a neighbour can take its value.
    """
    instance.close_gap()
