"""
The upstream backend API.

Vitriolic can mirror a season from any competition management platform for
which a *backend* exists, in the same way Django's authentication, e-mail,
cache and storage layers are pluggable. A backend is a subclass of
:class:`BaseUpstreamBackend`; the backends in use are named by the
``UPSTREAM_BACKENDS`` setting (see :mod:`tournamentcontrol.competition.upstream`)
and the rest of the application only ever talks to the base class API:

* which URLs belong to the backend, and what the organisation and season
  pages on its site look like (:meth:`~BaseUpstreamBackend.matches`,
  :meth:`~BaseUpstreamBackend.parse_competition_url`,
  :meth:`~BaseUpstreamBackend.parse_season_url`);
* how its own identifiers become the qualified ``upstream_id`` stored on a
  division, team or match (:meth:`~BaseUpstreamBackend.identifier` and its
  inverse, inherited and rarely overridden);
* how to fetch the complete snapshot of a season
  (:meth:`~BaseUpstreamBackend.fetch_snapshot`) as the backend-neutral types
  in :mod:`.types`, with :meth:`~BaseUpstreamBackend.new_client` giving the
  transport the tests replace.

Nothing here imports the ORM, so :mod:`tournamentcontrol.competition.models`
can import the registry to validate URLs and to name the backend a record
belongs to. This module also provides the error hierarchy every backend
raises and the HTTP transport they share.
"""

import logging
import re
from abc import ABC, abstractmethod
from typing import Optional

import requests
from django.core.exceptions import ImproperlyConfigured
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

USER_AGENT = "vitriolic-upstream-sync (+https://github.com/goodtune/vitriolic)"
DEFAULT_TIMEOUT = (5, 30)  # connect, read

# A backend key prefixes every upstream_id, so it must be URL-safe, lower
# case and free of the ":" that separates it from the remote identifier.
KEY_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class UpstreamError(Exception):
    """Base class for all upstream integration errors."""


class UpstreamURLError(UpstreamError, ValueError):
    """The configured URL is not one a backend recognises."""


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
    Shared transport for backend clients.

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
            raise UpstreamTransportError(f"HTTP {response.status_code} from {url}")
        return response


class BaseUpstreamBackend(ABC):
    """
    The interface every upstream backend implements.

    Subclasses set the class attributes and implement the abstract methods;
    the concrete methods on identifiers should not need overriding. A
    backend is stateless: one instance serves every request, and anything
    per-synchronisation lives in the client :meth:`new_client` returns or in
    :meth:`fetch_snapshot`.

    ``key``
        Prefixes every ``upstream_id`` the backend's records carry
        (``"mysideline"`` gives ``mysideline:69295321``). It must never change
        once data has been synchronised, and must be unique among the
        configured backends.

    ``name``
        What the admin shows to people ("MySideline").

    ``competition_url_example``, ``season_url_example``
        Shown in help and error text.
    """

    key: str = ""
    name: str = ""
    competition_url_example: str = ""
    season_url_example: str = ""

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<{type(self).__name__}: {self.key}>"

    @classmethod
    def check(cls) -> None:
        """
        Validate the class attributes. Called when the backend is loaded
        from ``UPSTREAM_BACKENDS``; raises
        :class:`~django.core.exceptions.ImproperlyConfigured`.
        """
        if not cls.key or not KEY_RE.match(cls.key):
            raise ImproperlyConfigured(
                f"{cls.__name__}.key must be a lower-case identifier such as "
                f"'mysideline', got {cls.key!r}"
            )
        if not cls.name:
            raise ImproperlyConfigured(f"{cls.__name__}.name must be set")

    # -- identifiers ---------------------------------------------------------

    def identifier(self, remote_id) -> str:
        """The ``upstream_id`` for one of this backend's own identifiers."""
        return f"{self.key}:{remote_id}"

    def owns_identifier(self, upstream_id: str) -> bool:
        return bool(upstream_id) and upstream_id.startswith(self.key + ":")

    def remote_id(self, upstream_id: str) -> str:
        """The backend's own identifier from an ``upstream_id`` it owns."""
        if not self.owns_identifier(upstream_id):
            raise ValueError(f"{upstream_id!r} does not belong to {self.name}")
        return upstream_id[len(self.key) + 1 :]

    # -- URLs ----------------------------------------------------------------

    @abstractmethod
    def matches(self, url: str) -> bool:
        """Whether ``url`` is on this backend's site."""

    @abstractmethod
    def parse_competition_url(self, url: str) -> str:
        """
        Validate and canonicalise the URL that links a ``Competition`` to an
        organisation on the provider. Raises :class:`UpstreamURLError`.
        """

    @abstractmethod
    def parse_season_url(self, url: str, competition_url: str) -> str:
        """
        Validate and canonicalise the URL that selects a ``Season``'s draws
        within the organisation ``competition_url`` names. Raises
        :class:`UpstreamURLError` when the URL is not understood or belongs
        to a different organisation.
        """

    # -- data ----------------------------------------------------------------

    @abstractmethod
    def new_client(self, session: Optional[requests.Session] = None) -> HttpClient:
        """
        The client :meth:`fetch_snapshot` uses when none is given. ``session``
        lets the tests substitute a canned ``requests.Session``.
        """

    @abstractmethod
    def fetch_snapshot(self, season, client: Optional[HttpClient] = None) -> list:
        """
        Fetch the complete remote snapshot for ``season`` -- a list of
        :class:`~tournamentcontrol.competition.upstream.types.RemoteCompetition`
        -- without touching the database. Any transport or parsing error
        propagates as an :class:`UpstreamError`; a partial snapshot is never
        returned.
        """
