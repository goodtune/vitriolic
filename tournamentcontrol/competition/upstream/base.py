"""
The pieces every upstream provider shares: the error hierarchy, the HTTP
transport and the :class:`UpstreamProvider` interface that the reconciler
in :mod:`.sync` and the admin forms program against.

A provider is a stateless object that knows three things:

* which URLs belong to it, and what the organisation and season pages on
  its site look like (:meth:`~UpstreamProvider.parse_competition_url`,
  :meth:`~UpstreamProvider.parse_season_url`);
* how to turn its own identifiers into the qualified ``upstream_id`` stored
  on a division, team or match (:meth:`~UpstreamProvider.identifier`);
* how to fetch the complete snapshot of a season
  (:meth:`~UpstreamProvider.fetch_snapshot`) as the provider-neutral types
  in :mod:`.types`.

Nothing here imports the ORM, so :mod:`tournamentcontrol.competition.models`
can import the registry to validate URLs and to name the provider a record
belongs to.
"""

import logging
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

USER_AGENT = "vitriolic-upstream-sync (+https://github.com/goodtune/vitriolic)"
DEFAULT_TIMEOUT = (5, 30)  # connect, read


class UpstreamError(Exception):
    """Base class for all upstream integration errors."""


class UpstreamURLError(UpstreamError, ValueError):
    """The configured URL is not one a provider recognises."""


class UpstreamTransportError(UpstreamError):
    """The remote service could not be reached or returned an HTTP error."""


class UpstreamResponseError(UpstreamError):
    """The remote service responded, but not with the expected structure."""


def new_session() -> requests.Session:
    """A ``requests`` session with modest retries on gateway errors."""
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class HttpClient:
    """
    Shared transport for provider clients.

    :meth:`request` raises :class:`UpstreamTransportError` when the network
    or HTTP layer fails; subclasses raise :class:`UpstreamResponseError` when
    a response cannot be understood. They never return partial data.
    """

    def __init__(self, session: Optional[requests.Session] = None, timeout=None):
        self.timeout = timeout or DEFAULT_TIMEOUT
        if session is None:
            session = new_session()
        session.headers.setdefault("User-Agent", USER_AGENT)
        self.session = session

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        try:
            response = self.session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            logger.warning("Upstream request failed: %s %s: %s", method, url, exc)
            raise UpstreamTransportError(str(exc)) from exc
        if response.status_code != 200:
            logger.warning(
                "Upstream unexpected status: %s %s -> %s",
                method,
                url,
                response.status_code,
            )
            raise UpstreamTransportError(
                "HTTP %d from %s" % (response.status_code, url)
            )
        return response


class UpstreamProvider:
    """
    Interface implemented by each provider module.

    ``key`` prefixes every ``upstream_id`` the provider's records carry and
    must never change once data has been synchronised; ``name`` is what the
    admin shows to people.
    """

    key: str = ""
    name: str = ""
    competition_url_example: str = ""
    season_url_example: str = ""

    def __str__(self):
        return self.name

    # -- identifiers ---------------------------------------------------------

    def identifier(self, remote_id) -> str:
        """The ``upstream_id`` for one of this provider's own identifiers."""
        return "%s:%s" % (self.key, remote_id)

    def owns_identifier(self, upstream_id: str) -> bool:
        return bool(upstream_id) and upstream_id.startswith(self.key + ":")

    def remote_id(self, upstream_id: str) -> str:
        """The provider's own identifier from an ``upstream_id`` it owns."""
        if not self.owns_identifier(upstream_id):
            raise ValueError("%r does not belong to %s" % (upstream_id, self.name))
        return upstream_id[len(self.key) + 1 :]

    # -- URLs ----------------------------------------------------------------

    def matches(self, url: str) -> bool:
        """Whether ``url`` is on this provider's site."""
        raise NotImplementedError

    def parse_competition_url(self, url: str) -> str:
        """
        Validate and canonicalise the URL that links a ``Competition`` to an
        organisation on the provider. Raises :class:`UpstreamURLError`.
        """
        raise NotImplementedError

    def parse_season_url(self, url: str, competition_url: str) -> str:
        """
        Validate and canonicalise the URL that selects a ``Season``'s draws
        within the organisation ``competition_url`` names. Raises
        :class:`UpstreamURLError` when the URL is not understood or belongs
        to a different organisation.
        """
        raise NotImplementedError

    # -- data ----------------------------------------------------------------

    def new_client(self, session: Optional[requests.Session] = None) -> HttpClient:
        raise NotImplementedError

    def fetch_snapshot(self, season, client: Optional[HttpClient] = None) -> list:
        """
        Fetch the complete remote snapshot for ``season`` -- a list of
        :class:`~tournamentcontrol.competition.upstream.types.RemoteCompetition`
        -- without touching the database. Any transport or parsing error
        propagates; a partial snapshot is never returned.
        """
        raise NotImplementedError
