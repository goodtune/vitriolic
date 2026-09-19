"""
Typed representations of the MySideline entities consumed by the reconciler.

These are deliberately minimal: they carry only the data that Vitriolic needs
to reproduce the competition structure, draw and results. Raw API responses
are normalised into these types by :mod:`.client` so that the reconciler in
:mod:`.sync` never has to reason about the shape of the remote payload.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Match status values observed on MySideline. Anything else is treated as
# "not yet played" so that an unexpected status never fabricates a result.
STATUS_PRE_GAME = "pre-game"
STATUS_FINAL = "final"
STATUS_FORFEIT = "forfeit"

# Round types observed on MySideline.
ROUND_REGULAR = "Regular"
ROUND_FINAL = "Final"


class RemoteCompetitionSummary(BaseModel):
    """A competition as listed on an association page."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    season: int
    season_tag: Optional[int] = None
    is_active: bool = True


class RemoteVenue(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    timezone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class RemoteTeam(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    pool: Optional[str] = None


class RemoteMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    round_number: int
    round_type: str
    round_name: str
    start: Optional[datetime] = None
    status: str = STATUS_PRE_GAME
    home_team_id: Optional[int] = None
    away_team_id: Optional[int] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    is_bye: bool = False
    is_tba: bool = False
    forfeiting_team_id: Optional[int] = None
    venue: Optional[RemoteVenue] = None
    field: Optional[str] = None

    @property
    def is_final_round(self) -> bool:
        return self.round_type == ROUND_FINAL

    @property
    def has_result(self) -> bool:
        return self.status == STATUS_FINAL and not self.is_bye

    @property
    def is_forfeit(self) -> bool:
        return self.status == STATUS_FORFEIT


class RemoteLadderTemplate(BaseModel):
    """
    The ladder points scheme MySideline applies to a competition. Only used
    to seed a division's ladder configuration when it is created; the
    administrator remains free to change it afterwards.
    """

    model_config = ConfigDict(frozen=True)

    name: Optional[str] = None
    points_win: int = 3
    points_draw: int = 2
    points_loss: int = 1
    points_bye: int = 3
    points_forfeit_for: int = 3
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
        ]
        return " + ".join("%d*%s" % term for term in terms if term[0]) or "0*win"


class RemoteCompetition(BaseModel):
    """
    The complete snapshot of a single competition: its teams (with pool
    membership where the competition is pooled) and every fixture.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    teams: tuple[RemoteTeam, ...] = Field(default_factory=tuple)
    matches: tuple[RemoteMatch, ...] = Field(default_factory=tuple)
    ladder_template: Optional[RemoteLadderTemplate] = None

    @property
    def pools(self) -> tuple[str, ...]:
        """Distinct pool names in first-seen order."""
        seen: dict[str, None] = {}
        for team in self.teams:
            if team.pool:
                seen.setdefault(team.pool, None)
        return tuple(seen)

    @property
    def team_pool(self) -> dict[int, Optional[str]]:
        return {team.id: team.pool for team in self.teams}


class RemoteAssociation(BaseModel):
    """The competitions belonging to an association."""

    model_config = ConfigDict(frozen=True)

    id: int
    competitions: tuple[RemoteCompetitionSummary, ...] = Field(default_factory=tuple)


NationalId = Literal["TFA", "PRL"]
