"""Test helpers for Constance."""


class InMemoryRedis:
    """Minimal Redis-style client storing values in a shared dict."""

    _store = {}

    def get(self, key):
        return self._store.get(key)

    def mget(self, keys):
        if not keys:
            return []
        return [self.get(key) for key in keys]

    def set(self, key, value):
        self._store[key] = value
