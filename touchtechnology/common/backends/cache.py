import logging

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from redis.exceptions import ConnectionError
from redis_cache.cache import RedisCache as BaseRedisCache

logger = logging.getLogger(__name__)


class RedisCache(BaseRedisCache):
    """
    The standard redis_cache.RedisCache will throw ConnectionError exceptions
    when the backend cache is unavailable to it. This implementation will catch
    the exceptions and log the failure.

    We log at ERROR level all attempts that fail due to ConnectionError.
    We log at DEBUG level all attempts that succeed.
    """

    def get(self, key, default=None, version=None):
        """
        Wrap the underlying ``get``, returning ``default`` when the backend is
        unavailable.
        """
        try:
            hit = super(RedisCache, self).get(
                key, default=default, version=version)
        except ConnectionError as exc:
            hit = default
            logger.error('redis="get", key="%s", default="%s", version="%s", '
                         'result="miss", exception="%s"',
                         key, default, version, exc)
        else:
            logger.debug('redis="get", key="%s", default="%s", version="%s", '
                         'result="hit"', key, default, version)
        return hit

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        """
        Wrap the underlying ``set``, silently passing when the backend is
        unavailable.
        """
        if timeout == DEFAULT_TIMEOUT:
            timeout = self.default_timeout

        try:
            super(RedisCache, self).set(
                key, value, timeout=timeout, version=version)
        except ConnectionError as exc:
            logger.error('redis="set", key="%s", version="%s", timeout="%s", '
                         'result="miss", exception="%s"',
                         key, version, timeout, exc)
        else:
            logger.debug('redis="set", key="%s", version="%s", timeout="%s", '
                         'result="hit"', key, version, timeout)

    def delete(self, key, version=None):
        """
        Wrap the underlying ``delete``, silently passing when the backend is
        unavailable.
        """
        try:
            super(RedisCache, self).delete(key, version=version)
        except ConnectionError as exc:
            logger.error('redis="delete", key="%s", version="%s", '
                         'result="miss", exception="%s"',
                         key, version, exc)

    def clear(self):
        """
        Wrap the underlying ``clear``, silently passing when the backend is
        unavailable.
        """
        try:
            super(RedisCache, self).clear()
        except ConnectionError as exc:
            logger.error('redis="clear", result="miss", exception="%s"', exc)
