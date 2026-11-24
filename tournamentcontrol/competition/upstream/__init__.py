"""
Synchronisation of a :class:`~tournamentcontrol.competition.models.Season`
from an upstream competition management provider.

Sporting bodies publish their draws and results on a handful of hosted
platforms. Rather than have administrators re-key fixtures, a season can be
linked to the page on the provider that lists its draws and the provider is
then treated as authoritative: each synchronisation fetches a complete
snapshot and converges the local divisions, teams, fixtures and results onto
it (see ``docs/upstream.md``).

Providers are supported through pluggable *backends*, in the manner of
Django's authentication, e-mail and storage backends. The package is split
so that adding a provider means adding one backend class:

``base``
    :class:`~.base.BaseUpstreamBackend`, the API a backend implements, with
    the error hierarchy and the HTTP transport backends share.

``types``
    Typed, backend-neutral representations of the remote entities that the
    reconciler consumes. Nothing in here touches HTTP or the ORM.

``backends``
    One module per provider: :mod:`.backends.mysideline` and
    :mod:`.backends.revolutionise`.

``sync``
    Reconciliation of a season against a snapshot. Backend-neutral; records
    are matched on their qualified ``upstream_id``.

The backends in use are named by the ``UPSTREAM_BACKENDS`` setting, a list
of dotted paths to backend classes, which defaults to the two shipped here::

    UPSTREAM_BACKENDS = [
        "tournamentcontrol.competition.upstream.backends.mysideline.MySidelineBackend",
        "tournamentcontrol.competition.upstream.backends.revolutionise.RevolutioniseBackend",
    ]

The functions below are what the rest of the application uses to find the
backend for a URL or for a stored identifier.
"""

from functools import lru_cache
from typing import Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils.module_loading import import_string

from tournamentcontrol.competition.upstream.base import (
    BaseUpstreamBackend,
    HttpClient,
    UpstreamError,
    UpstreamResponseError,
    UpstreamTransportError,
    UpstreamURLError,
)

DEFAULT_UPSTREAM_BACKENDS = (
    "tournamentcontrol.competition.upstream.backends.mysideline.MySidelineBackend",
    "tournamentcontrol.competition.upstream.backends.revolutionise.RevolutioniseBackend",
)


def load_backend(path: str) -> BaseUpstreamBackend:
    """
    Import and instantiate the backend class at the dotted ``path``. Raises
    :class:`~django.core.exceptions.ImproperlyConfigured` when the path does
    not name a usable backend.
    """
    try:
        cls = import_string(path)
    except ImportError as exc:
        raise ImproperlyConfigured(
            f"UPSTREAM_BACKENDS entry {path!r} could not be imported: {exc}"
        ) from exc
    if not (isinstance(cls, type) and issubclass(cls, BaseUpstreamBackend)):
        raise ImproperlyConfigured(
            f"UPSTREAM_BACKENDS entry {path!r} is not a BaseUpstreamBackend subclass"
        )
    cls.check()
    try:
        return cls()
    except TypeError as exc:
        # An abstract method left unimplemented.
        raise ImproperlyConfigured(
            f"UPSTREAM_BACKENDS entry {path!r} cannot be instantiated: {exc}"
        ) from exc


@lru_cache(maxsize=1)
def _load_backends() -> tuple[BaseUpstreamBackend, ...]:
    paths = getattr(settings, "UPSTREAM_BACKENDS", DEFAULT_UPSTREAM_BACKENDS)
    if isinstance(paths, str):
        paths = (paths,)
    backends = []
    for path in paths:
        backend = load_backend(path)
        if any(other.key == backend.key for other in backends):
            raise ImproperlyConfigured(
                f"UPSTREAM_BACKENDS names two backends with the key {backend.key!r}"
            )
        backends.append(backend)
    return tuple(backends)


def get_backends() -> tuple[BaseUpstreamBackend, ...]:
    """The configured backends, in the order ``UPSTREAM_BACKENDS`` lists them."""
    return _load_backends()


@receiver(setting_changed)
def _reset_backends(sender=None, setting=None, **kwargs):
    if setting == "UPSTREAM_BACKENDS":
        _load_backends.cache_clear()


def get_backend_for_url(url: str) -> BaseUpstreamBackend:
    """The backend whose site ``url`` is on. Raises :class:`UpstreamURLError`."""
    for backend in get_backends():
        if backend.matches(url):
            return backend
    names = ", ".join(backend.name for backend in get_backends())
    raise UpstreamURLError(f"Not a URL on a supported provider ({names}): {url!r}")


def get_backend_by_key(key: str) -> BaseUpstreamBackend:
    """The backend with ``key``. Raises :class:`KeyError`."""
    for backend in get_backends():
        if backend.key == key:
            return backend
    raise KeyError(key)


def get_backend_for_identifier(upstream_id: str) -> Optional[BaseUpstreamBackend]:
    """The backend a stored ``upstream_id`` belongs to, or ``None``."""
    for backend in get_backends():
        if backend.owns_identifier(upstream_id):
            return backend
    return None


__all__ = [
    "DEFAULT_UPSTREAM_BACKENDS",
    "BaseUpstreamBackend",
    "HttpClient",
    "UpstreamError",
    "UpstreamResponseError",
    "UpstreamTransportError",
    "UpstreamURLError",
    "get_backend_by_key",
    "get_backend_for_identifier",
    "get_backend_for_url",
    "get_backends",
    "load_backend",
]
