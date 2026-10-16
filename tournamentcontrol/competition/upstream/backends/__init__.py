"""
The upstream backends shipped with Vitriolic, one module each.

A backend is a subclass of
:class:`~tournamentcontrol.competition.upstream.base.BaseUpstreamBackend`.
The backends in use are named by the ``UPSTREAM_BACKENDS`` setting (see
:mod:`tournamentcontrol.competition.upstream`), which defaults to the two
here; a deployment may add its own by listing the dotted path of its class.
"""
