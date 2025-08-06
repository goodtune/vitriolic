# -*- coding: utf-8 -*-

import logging
from typing import Any, Dict, List

from django.db import transaction
from django.utils.text import slugify

from tournamentcontrol.competition.ai import CompetitionPlan
from tournamentcontrol.competition.models import (
    Division,
    Match,
    Season,
    Stage,
    StageGroup,
    Team,
    UndecidedTeam,
)

logger = logging.getLogger(__name__)


class CompetitionExecutionError(Exception):
    """Exception raised during competition plan execution."""

    pass


@transaction.atomic
def execute_competition_plan(season: Season, plan: CompetitionPlan):
    """
    Execute a competition plan by creating the actual model instances.

    Args:
        season: The Season instance to populate
        plan: The CompetitionPlan to execute

    Raises:
        CompetitionExecutionError: If execution fails
    """
    try:
        logger.info(
            f"Executing competition plan for season {season.pk}: {plan.description}"
        )

        # Track created objects for cleanup on error
        created_divisions = []

        for division_plan in plan.divisions:
            division = _create_division(season, division_plan)
            created_divisions.append(division)

            # Track created teams for this division
            team_mapping = {}

            # Create teams for this division
            for i, team_name in enumerate(division_plan.teams):
                team = _create_team(division, team_name, i + 1)
                team_mapping[team_name] = team

            # Create stages and pools
            for stage_plan in division_plan.stages:
                stage = _create_stage(division, stage_plan)

                # Create pools (stage groups) for this stage
                for pool_plan in stage_plan.pools:
                    pool = _create_pool(stage, pool_plan)

                    # Add teams to pool
                    _assign_teams_to_pool(
                        pool, pool_plan, team_mapping, stage_plan.stage_type
                    )

                    # Generate matches for this pool if it's round robin
                    if stage_plan.stage_type == "round_robin":
                        _generate_round_robin_matches(pool, stage_plan)

        logger.info(f"Successfully executed plan for season {season.pk}")

    except Exception as e:
        logger.error(f"Error executing competition plan: {e}")
        raise CompetitionExecutionError(f"Failed to create competition structure: {e}")


def _create_division(season: Season, division_plan) -> Division:
    """Create a Division from the plan."""
    division = Division.objects.create(
        season=season,
        title=division_plan.name,
        slug=slugify(division_plan.name),
        description=division_plan.description,
        order=1,  # For now, just use order 1. Could be enhanced later.
        enabled=True,
    )

    logger.debug(f"Created division: {division.title}")
    return division


def _create_team(division: Division, team_name: str, order: int) -> Team:
    """Create a Team for the division."""
    # Check if this team already exists in the season
    existing_team = division.season.teams.filter(title=team_name).first()
    if existing_team:
        # If team exists, just ensure it's in this division
        if not existing_team.division_id:
            existing_team.division = division
            existing_team.save()
        return existing_team

    # Create new team
    team = Team.objects.create(
        division=division,
        title=team_name,
        slug=slugify(team_name),
        order=order,
        enabled=True,
    )

    logger.debug(f"Created team: {team.title}")
    return team


def _create_stage(division: Division, stage_plan) -> Stage:
    """Create a Stage from the plan."""
    # Map stage types to format choices
    format_mapping = {
        "round_robin": 1,  # Assuming 1 is round robin format
        "knockout": 2,  # Assuming 2 is knockout format
        "swiss": 3,  # Assuming 3 is swiss format
    }

    stage = Stage.objects.create(
        division=division,
        title=stage_plan.name,
        slug=slugify(stage_plan.name),
        description=stage_plan.description,
        order=1,  # Could be enhanced to handle multiple stages
        format=format_mapping.get(stage_plan.stage_type, 1),
        enabled=True,
    )

    logger.debug(f"Created stage: {stage.title}")
    return stage


def _create_pool(stage: Stage, pool_plan) -> StageGroup:
    """Create a Pool (StageGroup) from the plan."""
    pool = StageGroup.objects.create(
        stage=stage,
        title=pool_plan.name,
        slug=slugify(pool_plan.name),
        description=pool_plan.description,
        order=1,  # Could be enhanced for multiple pools
        enabled=True,
    )

    logger.debug(f"Created pool: {pool.title}")
    return pool


def _assign_teams_to_pool(
    pool: StageGroup, pool_plan, team_mapping: Dict[str, Team], stage_type: str
):
    """Assign teams to a pool."""
    for team_name in pool_plan.teams:
        if team_name in team_mapping:
            # Real team
            team = team_mapping[team_name]
            pool.teams.add(team)
        else:
            # This might be a placeholder like "Pool A Winner"
            # Create an UndecidedTeam for these
            undecided_team = UndecidedTeam.objects.create(
                division=pool.stage.division,
                title=team_name,
                slug=slugify(team_name),
                label=team_name,
                enabled=True,
            )
            pool.teams.add(undecided_team)

    logger.debug(f"Assigned {len(pool_plan.teams)} teams to pool {pool.title}")


def _generate_round_robin_matches(pool: StageGroup, stage_plan):
    """Generate round robin matches for a pool."""
    teams = list(pool.teams.all())

    if len(teams) < 2:
        return

    round_num = 1

    # Generate all possible pairings
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            team_a = teams[i]
            team_b = teams[j]

            match = Match.objects.create(
                stage=pool.stage,
                pool=pool,
                team_a=team_a,
                team_b=team_b,
                round=round_num,
                enabled=True,
                is_bye=False,
            )

            logger.debug(f"Created match: {team_a.title} vs {team_b.title}")

    logger.debug(
        f"Generated {len(teams) * (len(teams) - 1) // 2} matches for pool {pool.title}"
    )


def cleanup_season_structure(season: Season):
    """
    Clean up existing competition structure for a season.
    Warning: This will delete all divisions, stages, teams, and matches!
    """
    with transaction.atomic():
        # Delete in reverse dependency order
        season.matches.all().delete()
        season.teams.all().delete()

        for division in season.divisions.all():
            for stage in division.stages.all():
                stage.pools.all().delete()
                stage.delete()
            division.delete()

        logger.info(f"Cleaned up competition structure for season {season.pk}")
