from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError

from tournamentcontrol.competition.models import Season
from tournamentcontrol.competition.mysideline.client import (
    MySidelineClient,
    MySidelineError,
)
from tournamentcontrol.competition.mysideline.sync import (
    synchronise_all,
    synchronise_season,
)


class Command(BaseCommand):
    help = (
        "Synchronise seasons with MySideline. Without arguments every enabled, "
        "incomplete season with a MySideline URL is synchronised."
    )

    def add_arguments(self, parser: ArgumentParser):
        parser.add_argument(
            "season",
            nargs="*",
            type=int,
            help="Primary key(s) of the season(s) to synchronise.",
        )

    def handle(self, *args, **options):
        client = MySidelineClient()
        if not options["season"]:
            results = synchronise_all(client)
            for pk, result in results.items():
                self.stdout.write("season %d: %s" % (pk, result.summary()))
                for warning in result.warnings:
                    self.stdout.write(self.style.WARNING("  %s" % warning))
            return

        failed = False
        for pk in options["season"]:
            try:
                season = Season.objects.get(pk=pk)
            except Season.DoesNotExist:
                raise CommandError("Season %d does not exist" % pk)
            if not season.mysideline_url:
                raise CommandError("Season %d has no MySideline URL" % pk)
            try:
                result = synchronise_season(season, client)
            except MySidelineError as exc:
                failed = True
                self.stderr.write(self.style.ERROR("season %d: %s" % (pk, exc)))
                continue
            self.stdout.write("season %d: %s" % (pk, result.summary()))
            for warning in result.warnings:
                self.stdout.write(self.style.WARNING("  %s" % warning))
        if failed:
            raise CommandError("One or more seasons failed to synchronise")
