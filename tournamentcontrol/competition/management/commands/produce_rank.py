import argparse

from datetime import date
from dateutil.parser import parse as date_parse

from django.core.management import BaseCommand
from django.utils.module_loading import import_string


def decay_function(path):
    try:
        return import_string(path)
    except ImportError:
        msg = 'Invalid decay function "{}" specified'.format(path)
        raise argparse.ArgumentTypeError(msg)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--decay', default='tournamentcontrol.competition.rank.no_decay', type=decay_function)
        parser.add_argument('--start', type=date_parse)
        parser.add_argument('--at', type=date_parse)
        parser.add_argument('--json', type=argparse.FileType('wb'))

    def handle(self, start, at, decay, json, *args, **kwargs):
        from tournamentcontrol.competition.rank import rank, json_rank

        if not json:
            ranking_table = rank(start=start, at=at, decay=decay)
        else:
            json_rank(stream=json, start=start, at=at, decay=decay)
