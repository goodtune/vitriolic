"""
Typed, backend-neutral representations of the remote entities consumed by
the reconciler.

These are deliberately minimal: they carry only the data that Vitriolic needs
to reproduce the competition structure, draw and results. Each provider
module normalises its own responses into these types so that the reconciler
in :mod:`.sync` never has to reason about the shape of a remote payload.

Identifiers are the provider's own, as strings (an integer is accepted and
converted); the reconciler qualifies them with the provider's key before
storing them (see :meth:`~.base.BaseUpstreamBackend.identifier`).
"""

from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

# Match status values the reconciler understands. Anything else is treated
# as "not yet played" so that an unexpected status never fabricates a result.
STATUS_PRE_GAME = "pre-game"
STATUS_FINAL = "final"
STATUS_FORFEIT = "forfeit"
STATUS_IN_PROGRESS = "in-progress"

# Round types: a competition's fixtures are split into a regular season (with
# a ladder) and a finals series (without one) on this.
ROUND_REGULAR = "Regular"
ROUND_FINAL = "Final"


def _coerce_id(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


RemoteId = Annotated[str, BeforeValidator(_coerce_id)]


class RemoteVenue(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: RemoteId
    name: str
    timezone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class RemoteTeam(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: RemoteId
    name: str
    pool: Optional[str] = None


class RemoteMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: RemoteId
    round_number: int
    round_type: str
    round_name: str
    start: Optional[datetime] = None
    # Whether ``start`` carries a kick-off time, or only the day of the
    # fixture (a provider may publish a date with the time to be advised).
    has_time: bool = True
    status: str = STATUS_PRE_GAME
    home_team_id: Optional[RemoteId] = None
    away_team_id: Optional[RemoteId] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    is_bye: bool = False
    is_tba: bool = False
    forfeiting_team_id: Optional[RemoteId] = None
    venue: Optional[RemoteVenue] = None
    field: Optional[str] = None

    @property
    def is_final_round(self) -> bool:
        return self.round_type == ROUND_FINAL

    @property
    def has_result(self) -> bool:
        """
        Whether this match has been played and its score can be trusted.

        MySideline does not reliably promote a match to ``final`` once it has
        been played: most played matches keep the ``pre-game`` status they
        were created with while their score is published anyway. Trusting the
        status alone therefore discards real results, and because the
        reconciler writes ``None`` for a match without a result it also erases
        scores it imported earlier.

        A match that has started and carries a non-zero score has been played,
        so its score is taken regardless of status. An unplayed match always
        reports 0-0, and a match still being played is excluded so that a
        partial score is never mistaken for a final one. A provider that does
        know a match is complete reports it as ``final``, which is trusted as
        it stands (including a 0-0 draw).
        """
        if self.is_bye:
            return False
        if self.status == STATUS_FINAL:
            return True
        if self.status == STATUS_IN_PROGRESS:
            return False
        if self.start is None or self.start > datetime.now(timezone.utc):
            return False
        return bool(self.home_score or self.away_score)

    @property
    def is_forfeit(self) -> bool:
        return self.status == STATUS_FORFEIT


class RemoteLadderTemplate(BaseModel):
    """
    The ladder points scheme the provider applies to a competition. Only used
    to seed a division's ladder configuration when it is created; the
    administrator remains free to change it afterwards. The defaults are the
    Touch Football Australia standard ladder.
    """

    model_config = ConfigDict(frozen=True)

    name: Optional[str] = None
    points_win: int = 3
    points_draw: int = 2
    points_loss: int = 1
    points_bye: int = 3
    points_forfeit_for: int = 3
    points_forfeit_against: int = 0
    forfeit_score: int = 5
    forfeit_counts_as_played: bool = True

    @property
    def points_formula(self) -> str:
        terms = [
            (self.points_win, "win"),
            (self.points_draw, "draw"),
            (self.points_loss, "loss"),
            (self.points_bye, "bye"),
            (self.points_forfeit_for, "forfeit_for"),
            (self.points_forfeit_against, "forfeit_against"),
        ]
        return (
            " + ".join(f"{points}*{term}" for points, term in terms if points)
            or "0*win"
        )


class RemoteCompetition(BaseModel):
    """
    The complete snapshot of a single competition -- what becomes a
    ``Division`` locally: its teams (with pool membership where the
    competition is pooled) and every fixture.
    """

    model_config = ConfigDict(frozen=True)

    id: RemoteId
    name: str
    teams: tuple[RemoteTeam, ...] = Field(default_factory=tuple)
    matches: tuple[RemoteMatch, ...] = Field(default_factory=tuple)
    ladder_template: Optional[RemoteLadderTemplate] = None
    # Set when the provider could not supply a ladder template and the
    # division will be seeded with defaults that may need checking.
    warnings: tuple[str, ...] = Field(default_factory=tuple)

    @property
    def pools(self) -> tuple[str, ...]:
        """Distinct pool names in first-seen order."""
        seen: dict[str, None] = {}
        for team in self.teams:
            if team.pool:
                seen.setdefault(team.pool, None)
        return tuple(seen)

    @property
    def team_pool(self) -> dict[str, Optional[str]]:
        return {team.id: team.pool for team in self.teams}
