import json
from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError

from tournamentcontrol.competition.models import Division


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
            division_structure = division.to_division_structure()

            if output_format == "json":
                output = json.dumps(division_structure.model_dump(), indent=indent)
                self.stdout.write(output)
            else:
                self.stdout.write(repr(division_structure))

        except Exception as e:
            raise CommandError(f"Failed to reverse engineer division: {e}")
