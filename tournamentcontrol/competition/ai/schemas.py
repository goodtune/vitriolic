# -*- coding: utf-8 -*-

"""
Schema definitions for AI-generated tournament structures.

These Pydantic models define the structure that AI models should output
when generating tournament formats, with built-in JSON Schema generation.
"""

from typing import Dict, Optional

from pydantic import BaseModel, Field


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
