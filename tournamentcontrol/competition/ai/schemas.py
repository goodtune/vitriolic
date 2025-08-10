# -*- coding: utf-8 -*-

"""
Schema definitions for AI-generated tournament structures.

These dataclasses define the structure that AI models should output
when generating tournament formats.
"""

from dataclasses import dataclass


@dataclass
class PoolFixture:
    """Pool within a stage."""

    title: str
    draw_format: str
    teams: list[int] | None = None


@dataclass
class StageFixture:
    """Stage within a division."""

    title: str
    draw_format: str | None = None
    pools: list[PoolFixture] | None = None


@dataclass
class DivisionStructure:
    """Division structure matching the test fixture schema."""

    title: str
    teams: list[str]
    stages: list[StageFixture]
