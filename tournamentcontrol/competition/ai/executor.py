# -*- coding: utf-8 -*-

import itertools
import logging

from django.db import transaction
from django.utils.text import slugify

from tournamentcontrol.competition.ai import CompetitionPlan
from tournamentcontrol.competition.ai.schemas import DivisionStructure
from tournamentcontrol.competition.draw import DrawGenerator
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
            # Create division
            division, _ = Division.objects.get_or_create(
                season=season,
                title=division_plan.name,
                defaults={
                    "slug": slugify(division_plan.name),
                    "order": 1,
                },
            )
            created_divisions.append(division)
            logger.debug(f"Created division: {division.title}")

            # Track created teams for this division
            team_mapping = {}

            # Create teams for this division
            for i, team_name in enumerate(division_plan.teams):
                team, _ = Team.objects.get_or_create(
                    division=division,
                    title=team_name,
                    defaults={
                        "slug": slugify(team_name),
                        "order": i + 1,
                    },
                )
                team_mapping[team_name] = team
                logger.debug(f"Created team: {team.title}")

            # Create stages and pools
            for stage_order, stage_plan in enumerate(division_plan.stages, 1):
                stage, _ = Stage.objects.get_or_create(
                    division=division,
                    title=stage_plan.name,
                    defaults={
                        "slug": slugify(stage_plan.name),
                        "order": stage_order,
                    },
                )
                logger.debug(f"Created stage: {stage.title}")

                # Create pools (stage groups) for this stage
                for pool_order, pool_plan in enumerate(stage_plan.pools, 1):
                    pool, _ = StageGroup.objects.get_or_create(
                        stage=stage,
                        title=pool_plan.name,
                        defaults={
                            "slug": slugify(pool_plan.name),
                            "order": pool_order,
                        },
                    )
                    logger.debug(f"Created pool: {pool.title}")

                    # Add teams to pool
                    for team_name in pool_plan.teams:
                        if team_name in team_mapping:
                            # Real team
                            team = team_mapping[team_name]
                            pool.teams.add(team)
                        else:
                            # This might be a placeholder like "Pool A Winner"
                            # Create an UndecidedTeam for these
                            UndecidedTeam.objects.create(
                                stage=pool.stage,
                                stage_group=pool,
                                label=team_name,
                            )
                    logger.debug(
                        f"Assigned {len(pool_plan.teams)} teams to pool {pool.title}"
                    )

                    # Generate matches for this pool based on stage type
                    if stage_plan.stage_type == "round_robin":
                        _generate_round_robin_matches(pool)
                    elif stage_plan.stage_type == "knockout":
                        _generate_knockout_matches(pool)

                # Handle knockout stages with no pools - generate direct matches
                if stage_plan.stage_type == "knockout" and not stage_plan.pools:
                    _generate_knockout_matches_for_stage(stage)

        logger.info(f"Successfully executed plan for season {season.pk}")

    except Exception as e:
        logger.error(f"Error executing competition plan: {e}")
        raise CompetitionExecutionError(f"Failed to create competition structure: {e}")


def _generate_round_robin_matches(pool: StageGroup):
    """Generate round robin matches for a pool."""
    teams = list(pool.teams.all())

    if len(teams) < 2:
        return

    # Generate all possible pairings
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            home_team = teams[i]
            away_team = teams[j]

            Match.objects.create(
                stage=pool.stage,
                stage_group=pool,
                home_team=home_team,
                away_team=away_team,
            )

            logger.debug(f"Created match: {home_team.title} vs {away_team.title}")

    logger.debug(
        f"Generated {len(teams) * (len(teams) - 1) // 2} matches for pool {pool.title}"
    )


def _generate_knockout_matches(pool: StageGroup):
    """Generate knockout matches for a pool."""
    teams = list(pool.teams.all())
    undecided_teams = list(pool.undecided_teams.all())
    all_participants = teams + undecided_teams

    if len(all_participants) < 2:
        return

    # For a 4-team finals: 1st vs 2nd, 3rd vs 4th
    if len(all_participants) == 4:
        # Final match: 1st vs 2nd
        final_match = Match.objects.create(
            stage=pool.stage,
            stage_group=pool,
            home_team=teams[0] if len(teams) > 0 else None,
            away_team=teams[1] if len(teams) > 1 else None,
        )

        # Set eval fields for undecided teams if needed
        if len(undecided_teams) >= 2:
            # Assuming first two undecided teams are 1st and 2nd place
            final_match.home_team_eval = "1st"
            final_match.away_team_eval = "2nd"
            final_match.save()

        # Bronze playoff: 3rd vs 4th
        bronze_match = Match.objects.create(
            stage=pool.stage,
            stage_group=pool,
            home_team=teams[2] if len(teams) > 2 else None,
            away_team=teams[3] if len(teams) > 3 else None,
        )

        # Set eval fields for undecided teams if needed
        if len(undecided_teams) >= 4:
            bronze_match.home_team_eval = "3rd"
            bronze_match.away_team_eval = "4th"
            bronze_match.save()

        logger.debug(f"Generated 2 knockout matches for pool {pool.title}")

    else:
        # For other knockout formats, pair participants sequentially
        matches_created = 0
        for i in range(0, len(all_participants) - 1, 2):
            if i + 1 < len(all_participants):
                home_participant = all_participants[i]
                away_participant = all_participants[i + 1]

                Match.objects.create(
                    stage=pool.stage,
                    stage_group=pool,
                    home_team=(
                        home_participant if isinstance(home_participant, Team) else None
                    ),
                    away_team=(
                        away_participant if isinstance(away_participant, Team) else None
                    ),
                )
                matches_created += 1

        logger.debug(
            f"Generated {matches_created} knockout matches for pool {pool.title}"
        )


def _generate_knockout_matches_for_stage(stage: Stage):
    """Generate knockout matches directly for a stage without pools."""
    # For finals without pools, create matches directly on the stage
    # This handles positional progression from previous stages

    # Create 2 matches: 1st vs 2nd, 3rd vs 4th
    Match.objects.create(
        stage=stage,
        home_team_eval="1st",
        away_team_eval="2nd",
    )

    Match.objects.create(
        stage=stage,
        home_team_eval="3rd",
        away_team_eval="4th",
    )

    logger.debug(f"Generated 2 direct knockout matches for stage {stage.title}")


@transaction.atomic
def build(season: Season, spec: DivisionStructure) -> Division:
    """
    Build a Division with Teams, Stages, StageGroups, and Matches from a DivisionStructure.

    Args:
        season: The Season to create the division in
        spec: DivisionStructure specification

    Returns:
        The created Division instance

    Raises:
        CompetitionExecutionError: If building fails
    """
    try:
        logger.info(f"Building division '{spec.title}' for season {season.pk}")
        next_division_order = (
            max(season.divisions.values_list("order", flat=True), default=0) + 1
        )

        # Create division
        division, _ = Division.objects.get_or_create(
            season=season,
            title=spec.title,
            defaults={
                "slug": slugify(spec.title),
                "order": next_division_order,
            },
        )
        logger.debug(f"Created division: {division.title}")

        # Create teams
        team_mapping = {}
        for i, team_name in enumerate(spec.teams):
            team, _ = Team.objects.get_or_create(
                division=division,
                title=team_name,
                defaults={
                    "slug": slugify(team_name),
                    "order": i + 1,
                },
            )
            team_mapping[team_name] = team
            logger.debug(f"Created team: {team.title}")

        # Create lookup by team order for pools that reference by index
        team_lookup = {team.order: team for team in division.teams.all()}

        # Create stages with pools and matches
        for stage_order, stage_spec in enumerate(spec.stages, 1):
            stage, _ = Stage.objects.get_or_create(
                division=division,
                title=stage_spec.title,
                defaults={
                    "slug": slugify(stage_spec.title),
                    "order": stage_order,
                },
            )
            logger.debug(f"Created stage: {stage.title}")

            # Handle stage-level draw format (knockouts without pools)
            if stage_spec.draw_format_ref and not stage_spec.pools:
                draw_format = spec.get_draw_format(stage_spec.draw_format_ref)
                if draw_format:
                    _generate_matches_from_draw_format(stage, draw_format, team_mapping)

            # Handle pool-level draw formats
            if stage_spec.pools:
                for pool_order, pool_spec in enumerate(stage_spec.pools, 1):
                    pool, _ = StageGroup.objects.get_or_create(
                        stage=stage,
                        title=pool_spec.title,
                        defaults={
                            "slug": slugify(pool_spec.title),
                            "order": pool_order,
                        },
                    )
                    logger.debug(f"Created pool: {pool.title}")

                    # Add teams to pool and build team mapping
                    pool_team_mapping = {}
                    if pool_spec.teams:
                        for i, team_index in enumerate(pool_spec.teams):
                            # team_index is 0-based index into spec.teams, convert to 1-based order
                            team_order = team_index + 1
                            if team_order in team_lookup:
                                team = team_lookup[team_order]
                                pool.teams.add(team)
                                pool_team_mapping[str(i + 1)] = (
                                    team  # 1-based for draw formats
                                )

                    # Generate matches for this pool if draw format exists
                    if pool_spec.draw_format_ref:
                        draw_format = spec.get_draw_format(pool_spec.draw_format_ref)
                        if draw_format:
                            _generate_matches_from_draw_format(
                                stage, draw_format, pool_team_mapping, pool
                            )

        logger.info(f"Successfully built division '{spec.title}'")
        return division

    except Exception as e:
        logger.error(f"Error building division: {e}")
        raise CompetitionExecutionError(f"Failed to build division: {e}")


def _generate_matches_from_draw_format(
    stage: Stage, draw_format: str, team_mapping: dict, stage_group: StageGroup = None
):
    """
    Generate matches using DrawGenerator from a draw format string.

    Args:
        stage: The Stage to create matches for
        draw_format: Draw format string compatible with DrawGenerator
        team_mapping: Mapping from team references to Team instances
        stage_group: Optional StageGroup for pool-level matches
    """
    try:
        # Create a temporary DrawGenerator instance with no start date (uses fallback mode)
        generator = DrawGenerator(stage, start_date=None)

        # Override the team mapping - DrawGenerator expects 0-based indexing
        generator.teams.update(
            {i: team for i, team in enumerate(team_mapping.values())}
        )

        # Parse the draw format
        generator.parse(draw_format)

        # Generate matches using custom date generator that returns None dates
        def no_date_generator(stage, start_date):
            return itertools.cycle([None])

        matches = generator.generate(custom_date_generator=no_date_generator)

        # Update stage_group for pool matches
        if stage_group:
            for match in matches:
                match.stage_group = stage_group

        # Save all matches
        matches.save()

        logger.debug(
            f"Generated {len(matches)} matches from draw format for {'pool ' + stage_group.title if stage_group else 'stage ' + stage.title}"
        )

    except Exception as e:
        logger.error(f"Error generating matches from draw format: {e}")
        raise


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
