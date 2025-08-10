# -*- coding: utf-8 -*-

"""
Schema definitions for AI-generated tournament structures.

These attrs-based classes define the structure that AI models should output
when generating tournament formats, with built-in JSON serialization.
"""

import json

import attrs
import cattrs


@attrs.define
class PoolFixture:
    """Pool within a stage."""

    title: str
    draw_format: str
    teams: list[int] | None = None


@attrs.define
class StageFixture:
    """Stage within a division."""

    title: str
    draw_format: str | None = None
    pools: list[PoolFixture] | None = None


@attrs.define
class DivisionStructure:
    """Division structure matching the test fixture schema."""

    title: str
    teams: list[str]
    stages: list[StageFixture]

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(cattrs.unstructure(self), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "DivisionStructure":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cattrs.structure(data, cls)
