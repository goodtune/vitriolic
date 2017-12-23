import logging
from functools import wraps

logger = logging.getLogger(__name__)


def disable_for_loaddata(signal_handler):
    """
    Decorator that turns off signal handlers when loading
    fixture data.
    """
    @wraps(signal_handler)
    def wrapper(*args, **kwargs):
        raw = kwargs.get('raw', False)
        if raw:
            instance = kwargs.get('instance')
            logger.debug('Skipping signal handler %r for instance %r.',
                         signal_handler, instance)
            return
        signal_handler(*args, **kwargs)
    return wrapper
