import json
import sys
import traceback
from argparse import ArgumentParser

from django.core.management.base import BaseCommand

from tournamentcontrol.competition.draw.schemas import DivisionStructure


class Command(BaseCommand):
    help = "Validate JSON against the DivisionStructure schema"

    def add_arguments(self, parser: ArgumentParser):
        parser.add_argument(
            "-f",
            "--filename",
            type=str,
            help="JSON file to validate (defaults to stdin)",
        )

    def handle(self, *args, **options):
        # Read JSON input
        if options["filename"]:
            try:
                with open(options["filename"], "r") as f:
                    json_data = json.load(f)
            except FileNotFoundError:
                self.stdout.write(
                    self.style.ERROR(f"File not found: {options['filename']}")
                )
                return
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.ERROR(f"Invalid JSON: {e}"))
                return
        else:
            try:
                json_data = json.load(sys.stdin)
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.ERROR(f"Invalid JSON: {e}"))
                return

        # Validate against schema
        try:
            division = DivisionStructure(**json_data)
            self.stdout.write(self.style.SUCCESS("Valid"))

            # Verbose mode 2: dump repr of object
            if options["verbosity"] >= 2:
                self.stdout.write("\n" + repr(division))

            # Verbose mode 3: dump all draw_formats
            if options["verbosity"] >= 3:
                self._dump_draw_formats(division)

        except Exception as e:
            # Always show basic error context, not just "Invalid"
            error_msg = f"Invalid: {type(e).__name__}: {e}"
            self.stdout.write(self.style.ERROR(error_msg))

            # Verbose mode shows full traceback
            if options["verbosity"] >= 2:
                self.stdout.write(self.style.ERROR("\nFull traceback:"))
                self.stdout.write(traceback.format_exc())

    def _dump_draw_formats(self, division: DivisionStructure):
        """Dump all draw_formats with their scope paths."""
        self.stdout.write("\n")

        # First, dump the draw_formats dictionary
        if division.draw_formats:
            self.stdout.write(
                self.style.HTTP_BAD_REQUEST("# Division Draw Formats Dictionary")
            )
            for format_name, draw_format_string in division.draw_formats.items():
                header = f"## {format_name}"
                self.stdout.write(self.style.HTTP_BAD_REQUEST(header))  # Magenta
                self.stdout.write(self.style.MIGRATE_LABEL(draw_format_string))  # Cyan
                self.stdout.write("")  # Empty line for readability

        # Then show how stages and pools reference them
        for stage_idx, stage in enumerate(division.stages):
            stage_path = f"stages[{stage_idx}]"

            # Stage-level draw format reference
            if stage.draw_format_ref:
                header = f"# {stage_path}.draw_format_ref = '{stage.draw_format_ref}'"
                if hasattr(stage, "title") and stage.title:
                    header += f" [Stage: {stage.title}]"
                self.stdout.write(self.style.HTTP_BAD_REQUEST(header))  # Magenta

                # Show resolved format
                draw_format = division.get_draw_format(stage.draw_format_ref)
                if draw_format:
                    self.stdout.write(self.style.MIGRATE_LABEL(draw_format))  # Cyan
                self.stdout.write("")  # Empty line for readability

            # Guard against None pools
            if stage.pools is None:
                continue

            for pool_idx, pool in enumerate(stage.pools):
                pool_path = f"{stage_path}.pools[{pool_idx}]"

                if pool.draw_format_ref:
                    # Build header with titles in brackets
                    header_parts = [
                        f"# {pool_path}.draw_format_ref = '{pool.draw_format_ref}'"
                    ]

                    # Add stage title if available
                    if hasattr(stage, "title") and stage.title:
                        header_parts.append(f"[Stage: {stage.title}]")

                    # Add pool title if available
                    if hasattr(pool, "title") and pool.title:
                        header_parts.append(f"[Pool: {pool.title}]")

                    header = " ".join(header_parts)

                    # Header in magenta, draw_format in cyan
                    self.stdout.write(self.style.HTTP_BAD_REQUEST(header))  # Magenta

                    # Show resolved format
                    draw_format = division.get_draw_format(pool.draw_format_ref)
                    if draw_format:
                        self.stdout.write(self.style.MIGRATE_LABEL(draw_format))  # Cyan
                    self.stdout.write("")  # Empty line for readability
