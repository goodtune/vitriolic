from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError

from tournamentcontrol.competition.models import Season
from tournamentcontrol.competition.upstream import UpstreamError
from tournamentcontrol.competition.upstream.sync import (
    synchronise_all,
    synchronise_season,
)


class Command(BaseCommand):
    help = (
        "Synchronise seasons with their upstream backend (MySideline, "
        "revolutioniseSPORT, ...). Without arguments every enabled, incomplete "
        "season linked to a backend is synchronised."
    )

    def add_arguments(self, parser: ArgumentParser):
        parser.add_argument(
            "season",
            nargs="*",
            type=int,
            help="Primary key(s) of the season(s) to synchronise.",
        )

    def handle(self, *args, **options):
        if not options["season"]:
            results = synchronise_all()
            for pk, result in results.items():
                self.stdout.write(f"season {pk}: {result.summary()}")
                for warning in result.warnings:
                    self.stdout.write(self.style.WARNING(f"  {warning}"))
            return

        failed = False
        clients = {}
        for pk in options["season"]:
            try:
                season = Season.objects.get(pk=pk)
            except Season.DoesNotExist:
                raise CommandError(f"Season {pk} does not exist")
            if not season.upstream_enabled:
                raise CommandError(
                    f"Season {pk} is not linked to an upstream backend (the "
                    "competition and the season both need an upstream URL)"
                )
            backend = season.upstream_backend
            if backend is None:
                raise CommandError(
                    f"Season {pk} is linked to an unsupported upstream URL"
                )
            client = clients.setdefault(backend.key, backend.new_client())
            try:
                result = synchronise_season(season, client)
            except UpstreamError as exc:
                failed = True
                self.stderr.write(self.style.ERROR(f"season {pk}: {exc}"))
                continue
            self.stdout.write(f"season {pk}: {result.summary()}")
            for warning in result.warnings:
                self.stdout.write(self.style.WARNING(f"  {warning}"))
        if failed:
            raise CommandError("One or more seasons failed to synchronise")
