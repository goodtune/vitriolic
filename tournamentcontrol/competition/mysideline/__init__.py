"""
MySideline (Touch Football Australia / NRL) integration.

MySideline is the competition management platform used by Touch Football
Australia. The public competition website (``https://tfa.mysideline.com.au``)
is a Next.js application that reads from a public GraphQL API operated by the
NRL (``https://community-backend.api.nationalrugbyleague.io/graphql``).

The integration is split into three layers:

``types``
    Typed, provider-neutral representations of the remote entities that the
    reconciler consumes. Nothing in here touches HTTP or the ORM.

``client``
    HTTP transport and parsing. Knows how to fetch an association's list of
    competitions and the teams, pools and matches for a competition, and how
    to normalise the raw responses into ``types``.

``sync``
    Reconciliation of a :class:`~tournamentcontrol.competition.models.Season`
    against a remote snapshot. MySideline is authoritative for everything it
    manages; the reconciler converges the local models onto the remote state.

See ``docs/mysideline.md`` for a description of the remote interface.
"""
