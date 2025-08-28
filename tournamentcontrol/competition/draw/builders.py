import itertools
import logging

from django.db import transaction
from django.utils.text import slugify

from tournamentcontrol.competition.models import (
    Division,
    Season,
    Stage,
    StageGroup,
    Team,
)

from .generators import DrawGenerator
from .schemas import CompetitionExecutionError

logger = logging.getLogger(__name__)


@transaction.atomic
def build(season: Season, spec) -> Division:
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
        # Only update if we have actual team mappings, otherwise let DrawGenerator
        # handle symbolic team references (like G1P1, W1, L2, etc.)
        if team_mapping:
            generator.teams.update(
                {i: team for i, team in enumerate(team_mapping.values())}
            )

        # Parse the draw format
        generator.parse(draw_format)

        # Generate matches using custom date generator that returns None dates
        def no_date_generator(stage, start_date):
            return itertools.cycle([None])

        matches = generator.generate(custom_date_generator=no_date_generator)

        logger.debug(f"DrawGenerator produced {len(matches)} matches")
        if len(matches) == 0:
            logger.warning(f"No matches generated from draw format: {draw_format[:100]}...")

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
