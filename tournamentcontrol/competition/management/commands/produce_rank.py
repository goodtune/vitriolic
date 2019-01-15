from __future__ import print_function

import argparse
import sys
from datetime import date

from dateutil.parser import parse as date_parse
from django.core.management import BaseCommand
from django.db import transaction
from django.utils.module_loading import import_string


def decay_function(path):
    try:
        return import_string(path)
    except ImportError:
        msg = 'Invalid decay function "{}" specified'.format(path)
        raise argparse.ArgumentTypeError(msg)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            '--decay',
            default='tournamentcontrol.competition.rank.no_decay',
            type=decay_function,
        )
        parser.add_argument('--start', type=date_parse)
        parser.add_argument('--at', type=date_parse)
        parser.add_argument('--json', type=argparse.FileType('wb'))
        parser.add_argument('--rebuild', action='store_true', default=False)

    def handle(self, start, at, decay, json, rebuild, *args, **kwargs):
        from tournamentcontrol.competition.models import RankPoints
        from tournamentcontrol.competition.rank import rank, json_rank

        if rebuild and at:
            dates = RankPoints.objects.filter(date__gte=at).dates('date', 'day')
        elif rebuild:
            dates = RankPoints.objects.dates('date', 'day')
        elif at is not None:
            dates = [at]
        else:
            dates = [date.today()]

        with transaction.atomic():
            for d in dates:
                if sys.stdout.isatty():
                    print(
                        "Producing ranking points for %s..." % (d.strftime("%Y-%m-%d"),)
                    )
                if not json:
                    rank(start=start, at=d, decay=decay)
                else:
                    json_rank(stream=json, start=start, at=d, decay=decay)
