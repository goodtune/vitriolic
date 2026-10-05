"""
Synchronisation of a :class:`~tournamentcontrol.competition.models.Season`
from an upstream competition management provider.

Sporting bodies publish their draws and results on a handful of hosted
platforms. Rather than have administrators re-key fixtures, a season can be
linked to the page on the provider that lists its draws and the provider is
then treated as authoritative: each synchronisation fetches a complete
snapshot and converges the local divisions, teams, fixtures and results onto
it (see ``docs/upstream.md``).

The package is split into layers so that adding a provider means adding one
module:

``base``
    The error hierarchy, the HTTP transport and the
    :class:`~.base.UpstreamProvider` interface.

``types``
    Typed, provider-neutral representations of the remote entities that the
    reconciler consumes. Nothing in here touches HTTP or the ORM.

``mysideline``, ``revolutionise``
    One module per provider: URL parsing, HTTP client and the normalisation
    of that provider's responses into ``types``.

``sync``
    Reconciliation of a season against a snapshot. Provider-neutral; records
    are matched on their qualified ``upstream_id``.

The registry below is what the rest of the application uses to find the
provider for a URL or for a stored identifier.
"""

from tournamentcontrol.competition.upstream.base import (
    HttpClient,
    UpstreamError,
    UpstreamProvider,
    UpstreamResponseError,
    UpstreamTransportError,
    UpstreamURLError,
)
from tournamentcontrol.competition.upstream.mysideline import MySidelineProvider
from tournamentcontrol.competition.upstream.revolutionise import (
    RevolutioniseProvider,
)

PROVIDERS: tuple[UpstreamProvider, ...] = (
    MySidelineProvider(),
    RevolutioniseProvider(),
)


def provider_for_url(url: str) -> UpstreamProvider:
    """The provider whose site ``url`` is on. Raises :class:`UpstreamURLError`."""
    for provider in PROVIDERS:
        if provider.matches(url):
            return provider
    raise UpstreamURLError(
        "Not a URL on a supported provider (%s): %r"
        % (", ".join(provider.name for provider in PROVIDERS), url)
    )


def provider_for_key(key: str) -> UpstreamProvider:
    for provider in PROVIDERS:
        if provider.key == key:
            return provider
    raise KeyError(key)


def provider_for_identifier(upstream_id: str):
    """The provider a stored ``upstream_id`` belongs to, or ``None``."""
    for provider in PROVIDERS:
        if provider.owns_identifier(upstream_id):
            return provider
    return None


__all__ = [
    "PROVIDERS",
    "HttpClient",
    "UpstreamError",
    "UpstreamProvider",
    "UpstreamResponseError",
    "UpstreamTransportError",
    "UpstreamURLError",
    "provider_for_identifier",
    "provider_for_key",
    "provider_for_url",
]
