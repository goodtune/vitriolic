import json
from argparse import ArgumentParser
from collections import OrderedDict
from typing import Dict, List, Optional

from django.core.management.base import BaseCommand, CommandError

from tournamentcontrol.competition.ai.schemas import (
    DivisionStructure,
    PoolFixture,
    StageFixture,
)
from tournamentcontrol.competition.models import (
    Division,
    Match,
    Stage,
    StageGroup,
    Team,
)


class Command(BaseCommand):
    help = "Reverse engineer a DivisionStructure from an existing division"

    def add_arguments(self, parser: ArgumentParser):
        parser.add_argument(
            "division_id",
            type=int,
            help="Division ID to reverse engineer",
        )
        parser.add_argument(
            "--output",
            choices=["json", "python"],
            default="json",
            help="Output format (default: json)",
        )
        parser.add_argument(
            "--indent",
            type=int,
            default=2,
            help="JSON indentation level (default: 2)",
        )

    def handle(self, **options):
        division_id = options["division_id"]
        output_format = options["output"]
        indent = options["indent"]

        try:
            division = Division.objects.get(pk=division_id)
        except Division.DoesNotExist:
            raise CommandError(f"Division with ID {division_id} does not exist")

        self.stderr.write(f"Reverse engineering division: {division.title}")
        self.stderr.write(f"Season: {division.season.title}")
        self.stderr.write("")

        try:
            division_structure = self._reverse_engineer(division)

            if output_format == "json":
                output = json.dumps(division_structure.model_dump(), indent=indent)
                self.stdout.write(output)
            else:
                self.stdout.write(repr(division_structure))

        except Exception as e:
            raise CommandError(f"Failed to reverse engineer division: {e}")

    def _reverse_engineer(self, division: Division) -> DivisionStructure:
        """Reverse engineer a DivisionStructure from a Division."""
        # Check for UndecidedTeam entries
        for stage in division.stages.all():
            if stage.undecided_teams.exists():
                raise CommandError(
                    f"Stage '{stage.title}' contains UndecidedTeam entries. "
                    "Cannot reverse engineer divisions with undecided teams yet."
                )
            for pool in stage.pools.all():
                if pool.undecided_teams.exists():
                    raise CommandError(
                        f"Pool '{pool.title}' in stage '{stage.title}' contains UndecidedTeam entries. "
                        "Cannot reverse engineer divisions with undecided teams yet."
                    )

        # Get all teams
        teams = list(division.teams.values_list("title", flat=True))

        # Collect all unique draw formats and build dictionary
        draw_formats = {}
        draw_format_refs = {}  # Maps draw_format_string -> ref_name

        # Process stages and collect draw formats
        stages = []
        for stage in division.stages.order_by("order"):
            stage_fixture = self._process_stage(
                stage, teams, draw_formats, draw_format_refs
            )
            stages.append(stage_fixture)

        return DivisionStructure(
            title=division.title, teams=teams, draw_formats=draw_formats, stages=stages
        )

    def _process_stage(
        self, stage: Stage, teams: List[str], draw_formats: Dict, draw_format_refs: Dict
    ) -> StageFixture:
        """Process a stage and return a StageFixture."""
        pools = stage.pools.order_by("order")

        if pools.exists():
            # Stage has pools
            pool_fixtures = []
            for pool in pools:
                pool_fixture = self._process_pool(
                    pool, teams, draw_formats, draw_format_refs
                )
                pool_fixtures.append(pool_fixture)

            return StageFixture(
                title=stage.title,
                draw_format_ref=None,  # Pool stages don't have stage-level draw_format
                pools=pool_fixtures,
            )
        else:
            # Stage without pools - knockout stage
            matches = stage.matches.order_by("round", "pk")
            draw_format_string = self._generate_draw_format(matches, teams)
            draw_format_ref = self._get_or_create_draw_format_ref(
                draw_format_string,
                f"{stage.title} Format",
                draw_formats,
                draw_format_refs,
            )

            return StageFixture(
                title=stage.title, draw_format_ref=draw_format_ref, pools=None
            )

    def _process_pool(
        self,
        pool: StageGroup,
        teams: List[str],
        draw_formats: Dict,
        draw_format_refs: Dict,
    ) -> PoolFixture:
        """Process a pool and return a PoolFixture."""
        # Get teams in this pool
        pool_teams = []
        pool_matches = pool.matches.all()

        # Extract unique teams from matches
        team_ids = set()
        for match in pool_matches:
            if match.home_team:
                team_ids.add(match.home_team.pk)
            if match.away_team:
                team_ids.add(match.away_team.pk)

        # Get team titles and convert to indices
        pool_team_objects = list(Team.objects.filter(pk__in=team_ids).order_by("title"))
        for team in pool_team_objects:
            try:
                pool_teams.append(teams.index(team.title))
            except ValueError:
                raise CommandError(
                    f"Team '{team.title}' not found in division teams list"
                )

        # Generate draw format
        matches = pool.matches.order_by("round", "pk")
        draw_format_string = self._generate_draw_format(
            matches, teams, pool_team_objects
        )
        draw_format_ref = self._get_or_create_draw_format_ref(
            draw_format_string, f"{pool.title} Format", draw_formats, draw_format_refs
        )

        return PoolFixture(
            title=pool.title, draw_format_ref=draw_format_ref, teams=pool_teams
        )

    def _generate_draw_format(
        self, matches, all_teams: List[str], pool_teams: Optional[List[Team]] = None
    ) -> str:
        """Generate a draw_format string from matches."""
        if not matches.exists():
            return ""

        # Sort by database ID for deterministic ordering (reflects creation order)
        match_list = list(matches.order_by("id"))

        # Create mapping from database ID to sequential match ID
        db_id_to_match_id = {match.id: idx + 1 for idx, match in enumerate(match_list)}

        # Group matches by round
        rounds: Dict[int, List[Match]] = OrderedDict()
        for match in match_list:
            round_num = match.round or 1
            if round_num not in rounds:
                rounds[round_num] = []
            rounds[round_num].append(match)

        draw_lines = []

        for round_num in sorted(rounds.keys()):
            if len(rounds) > 1:  # Only add ROUND headers if multiple rounds
                draw_lines.append("ROUND")

            for match in rounds[round_num]:
                match_id = db_id_to_match_id[match.id]
                line_parts = [str(match_id) + ":"]

                # Get home team
                home_team = self._get_team_identifier(
                    match, "home", all_teams, pool_teams, db_id_to_match_id
                )

                # Get away team
                away_team = self._get_team_identifier(
                    match, "away", all_teams, pool_teams, db_id_to_match_id
                )

                line_parts.append(f"{home_team} vs {away_team}")

                # Add label if present
                if match.label:
                    line_parts.append(match.label)

                draw_lines.append(" ".join(line_parts))

        return "\n".join(draw_lines)

    def _get_team_identifier(
        self,
        match: Match,
        side: str,
        all_teams: List[str],
        pool_teams: Optional[List[Team]] = None,
        db_id_to_match_id: Optional[Dict[int, int]] = None,
    ) -> str:
        """Get the team identifier for a match side (home/away)."""
        team = getattr(match, f"{side}_team")
        team_undecided = getattr(match, f"{side}_team_undecided")
        team_eval = getattr(match, f"{side}_team_eval")
        team_eval_related = getattr(match, f"{side}_team_eval_related")

        if team_undecided:
            # UndecidedTeam - use formula
            return team_undecided.formula

        elif team_eval:
            # Handle W/L references that need match IDs
            if team_eval in ["W", "L"] and team_eval_related and db_id_to_match_id:
                # Look up the match ID using the database ID mapping
                related_match_id = db_id_to_match_id.get(team_eval_related.id)
                if related_match_id:
                    return f"{team_eval}{related_match_id}"
            # Direct eval string (W1, L1, G1P1, etc.) - already complete
            return team_eval

        elif match.is_bye:
            # Bye match - whichever side is unset should be 0
            return "0"

        elif team:
            # Regular team
            if pool_teams:
                # For pool matches, use 1-based index within the pool
                try:
                    return str(pool_teams.index(team) + 1)
                except ValueError:
                    # Fallback to global team index
                    return str(all_teams.index(team.title) + 1)
            else:
                # For knockout matches, use global team index
                return str(all_teams.index(team.title) + 1)

        else:
            # Unknown - shouldn't happen but handle gracefully
            return "?"

    def _get_or_create_draw_format_ref(
        self,
        draw_format_string: str,
        format_name: str,
        draw_formats: Dict,
        draw_format_refs: Dict,
    ) -> Optional[str]:
        """Get or create a reference for a draw format string."""
        if not draw_format_string:
            return None

        # Check if we already have this format
        if draw_format_string in draw_format_refs:
            return draw_format_refs[draw_format_string]

        # Use the format name as the key (make it unique if needed)
        ref_name = format_name
        counter = 1
        while ref_name in draw_formats:
            counter += 1
            ref_name = f"{format_name} {counter}"

        draw_format_refs[draw_format_string] = ref_name
        draw_formats[ref_name] = draw_format_string

        return ref_name
