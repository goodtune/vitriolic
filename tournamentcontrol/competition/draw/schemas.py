import re
from typing import Dict, Optional

from pydantic import BaseModel, Field

WIN_LOSE_RE = re.compile(r"(?P<result>[WL])(?P<match_id>\d+)")


class PoolFixture(BaseModel):
    """Pool within a stage."""

    title: str = Field(..., description="Name of the pool (e.g., 'Pool A', 'Group 1')")
    draw_format_ref: Optional[str] = Field(
        None,
        description="Reference to a draw format in the division's draw_formats dictionary. Required for pool stages, should be null for knockout stages.",
    )
    teams: Optional[list[int]] = Field(
        None,
        description="Team indices for this pool (0-based indices into division teams array), or null for pools that reference other stage results",
    )


class StageFixture(BaseModel):
    """Stage within a division."""

    title: str = Field(..., description="Name of the tournament stage")
    draw_format_ref: Optional[str] = Field(
        None,
        description="Reference to a draw format in the division's draw_formats dictionary for direct knockout stages. Set to null for pool-based stages.",
    )
    pools: Optional[list[PoolFixture]] = Field(
        None,
        description="Pools within this stage for round-robin play. Set to null for direct knockout stages.",
    )


class DivisionStructure(BaseModel):
    """Division structure matching the test fixture schema."""

    title: str = Field(..., description="Name of the tournament division")
    teams: list[str] = Field(
        ...,
        min_length=2,
        description="List of team names participating in the tournament",
    )
    draw_formats: Dict[str, str] = Field(
        ...,
        description="Dictionary of reusable draw formats referenced by stages and pools. Keys are descriptive names, values are draw format strings using DrawGenerator syntax.",
    )
    stages: list[StageFixture] = Field(
        ..., min_length=1, description="Tournament stages in chronological order"
    )

    @classmethod
    def get_json_schema(cls) -> dict:
        """Generate JSON Schema from Pydantic model."""
        return cls.model_json_schema()

    def get_draw_format(self, ref: Optional[str]) -> Optional[str]:
        """Get the draw format string by reference."""
        if ref is None:
            return None
        return self.draw_formats.get(ref)

    def stage_draw_format_refs(self, stage: StageFixture) -> list[Optional[str]]:
        """
        The references to the draw formats the matches of ``stage`` are
        built from: its own when it has no pools, otherwise each pool's.
        """
        if stage.pools:
            return [pool.draw_format_ref for pool in stage.pools]
        return [stage.draw_format_ref]

    def stage_draw_formats(self, stage: StageFixture) -> list[str]:
        """
        The draw formats the matches of ``stage`` are built from. A
        reference to no format is left out, as the builder leaves it out.
        """
        refs = self.stage_draw_format_refs(stage)
        return [text for text in map(self.get_draw_format, refs) if text]

    def referenced_draw_formats(self) -> Dict[str, str]:
        """
        The draw formats some stage or pool refers to, by key, in the order
        they are first referred to. A reference to no format is left out.
        """
        refs = dict.fromkeys(
            ref for stage in self.stages for ref in self.stage_draw_format_refs(stage)
        )
        return {ref: self.draw_formats[ref] for ref in refs if ref in self.draw_formats}


class RoundDescriptor:
    def __init__(self, count, round_label, **kwargs):
        self.count = count
        self.round_label = round_label
        self.matches = []

    def add(self, match):
        self.matches.append(match)

    def generate(self, generator, stage, date):
        return [m.generate(generator, stage, self, date) for m in self.matches]

    def __str__(self):
        return "\n".join(
            [f"ROUND {self.round_label}"] + [str(m) for m in self.matches]
        )


class MatchDescriptor:
    def __init__(self, match_id, home_team, away_team, match_label=None, **kwargs):
        self.match_id = match_id
        self.home_team = home_team
        self.away_team = away_team
        self.match_label = match_label

    def __str__(self):
        if self.match_label:
            return (
                f"{self.match_id}: {self.home_team} vs {self.away_team} "
                f"{self.match_label}"
            )
        return f"{self.match_id}: {self.home_team} vs {self.away_team}"

    def generate(self, generator, stage, round, date):
        from tournamentcontrol.competition.models import (
            Match,
            Stage,
            StageGroup,
            Team,
            UndecidedTeam,
        )

        if isinstance(stage, StageGroup):
            stages = {
                "stage": stage.stage,
                "stage_group": stage,
            }
            include_in_ladder = stage.stage.keep_ladder
        else:
            stages = {"stage": stage}
            include_in_ladder = stage.keep_ladder

        match = Match(
            label=self.match_label or round.round_label,
            include_in_ladder=include_in_ladder,
            round=round.count,
            date=date,
            **stages,
        )

        setattr(match, "descriptor", self)

        home_team = generator.team(self.home_team)
        away_team = generator.team(self.away_team)

        if home_team is None:
            match.is_bye = True
        elif isinstance(home_team, UndecidedTeam):
            match.home_team_undecided = home_team
        elif isinstance(home_team, Team):
            match.home_team = home_team
        else:
            match.home_team_eval = home_team

        if away_team is None:
            match.is_bye = True
        elif isinstance(away_team, UndecidedTeam):
            match.away_team_undecided = away_team
        elif isinstance(away_team, Team):
            match.away_team = away_team
        else:
            match.away_team_eval = away_team

        if match.home_team_eval or match.away_team_eval:
            match.evaluated = False

        return (self.match_id, match)


class CompetitionExecutionError(Exception):
    """Exception raised during competition plan execution."""
