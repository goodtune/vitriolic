# -*- coding: utf-8 -*-

"""
Schema definitions for AI-generated tournament structures.

These Pydantic models define the structure that AI models should output
when generating tournament formats, with built-in JSON Schema generation.
"""

from typing import Optional

from pydantic import BaseModel, Field


class PoolFixture(BaseModel):
    """Pool within a stage."""

    title: str = Field(
        ..., 
        description="Name of the pool (e.g., 'Pool A', 'Group 1')"
    )
    draw_format: str = Field(
        ..., 
        description="Draw format string for this pool. Use DrawGenerator syntax for round-robin: 'ROUND\\n1: 1 vs 2\\n2: 3 vs 4\\nROUND\\n3: 1 vs 3\\n4: 2 vs 4'"
    )
    teams: Optional[list[int]] = Field(
        None, 
        description="Team indices for this pool (0-based indices into division teams array), or null for pools that reference other stage results"
    )


class StageFixture(BaseModel):
    """Stage within a division."""

    title: str = Field(
        ..., 
        description="Name of the tournament stage"
    )
    draw_format: Optional[str] = Field(
        None, 
        description="Draw format string for direct knockout stages. Use DrawGenerator syntax: 'ROUND\\n1: 1 vs 2 Semi\\nROUND\\n3: W1 vs W2 Final'. Set to null for pool-based stages."
    )
    pools: Optional[list[PoolFixture]] = Field(
        None, 
        description="Pools within this stage for round-robin play. Set to null for direct knockout stages."
    )


class DivisionStructure(BaseModel):
    """Division structure matching the test fixture schema."""

    title: str = Field(
        ..., 
        description="Name of the tournament division"
    )
    teams: list[str] = Field(
        ..., 
        min_length=2,
        description="List of team names participating in the tournament"
    )
    stages: list[StageFixture] = Field(
        ..., 
        min_length=1,
        description="Tournament stages in chronological order"
    )

    @classmethod
    def get_json_schema(cls) -> dict:
        """Generate JSON Schema from Pydantic model."""
        return cls.model_json_schema()
