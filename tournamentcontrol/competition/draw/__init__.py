"""
Tournament draw generation and management system.

This module provides a complete system for generating tournament draws and managing
competition structures. It has been restructured to separate pure algorithms from
Django model-dependent operations for better maintainability and testability.

Module Structure:
- schemas: Pydantic models and data structures (no Django dependencies)
- algorithms: Pure calculation functions and utilities
- generators: Django-dependent draw generation and match creation
- builders: Django ORM operations for creating competition structures

Import from specific submodules:
    from .schemas import DivisionStructure, PoolFixture, StageFixture
    from .algorithms import optimum_tournament_pool_count, seeded_tournament
    from .generators import DrawGenerator, MatchCollection
    from .builders import build, cleanup_season_structure
"""
