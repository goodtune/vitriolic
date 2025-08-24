import datetime
import functools
import logging
from decimal import Decimal

from dateutil.rrule import DAILY, WEEKLY, rrule, rruleset
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from first import first

from tournamentcontrol.competition.utils import (
    ceiling,
    final_series_rounds,
    grouper,
    round_robin_format,
    single_elimination_final_format,
)

logger = logging.getLogger(__name__)


def coerce_datetime(start_date):
    """
    When operating with time zone aware objects we're better off converting
    our plain old date instances to datetime instances before handing them
    to the rruleset.

    The datetime will be set to the current timezone.
    """
    if isinstance(start_date, datetime.date):
        start_date = datetime.datetime.combine(start_date, datetime.time())
    if not timezone.is_aware(start_date):
        start_date = timezone.make_aware(start_date, timezone.get_current_timezone())
    return start_date


def optimum_tournament_pool_count(
    number_of_teams, days_available, max_per_day=1, min_per_day=1
):
    """
    Using the available input variables, decide how many pools to divide a
    division into.

    :param number_of_teams: number of teams that make up the division
    :type number_of_teams: int
    :param days_available: number of days available for play
    :type days_available: int
    :param max_per_day: max number of games a team may play in one day
    :type max_per_day: int
    :param min_per_day: min number of prelim games a team must play in one day
    :type min_per_day: int
    :return: number of pools to split the division into
    :rtype: decimal.Decimal or None
    """
    # turn all of our input into Decimal types
    number_of_teams = Decimal(number_of_teams)
    days_available = Decimal(days_available)
    max_per_day = Decimal(max_per_day)
    min_per_day = Decimal(min_per_day)

    for n in range(4):
        number_of_pools = pow(2, n)
        largest_pool_size = ceiling(number_of_teams / number_of_pools)
        # smallest_pool_size = floor(number_of_teams / number_of_pools)
        preliminary_rounds = largest_pool_size - 1
        elimination_rounds = final_series_rounds(number_of_pools)
        elimination_days = ceiling(elimination_rounds / max_per_day, 0.5)
        total_rounds = preliminary_rounds + elimination_rounds
        days_required = total_rounds / max_per_day

        # Make sure we are playing enough games per day through preliminary
        # stage of the tournament.
        if preliminary_rounds / max_per_day > days_available - elimination_days:
            logger.warning(
                "Too many games (%s) to be played before the finals with %s pools.",
                preliminary_rounds,
                number_of_pools,
            )
            continue

        # Make sure we are playing enough games during the preliminary stages
        if preliminary_rounds / max_per_day > days_available - elimination_days:
            logger.warning(
                "Not enough time (%s days) to play %s games at %s games per day.",
                days_available - elimination_days,
                preliminary_rounds,
                max_per_day,
            )
            continue

        if days_required <= days_available:
            return number_of_pools


def seeded_tournament(seeded_team_list, days_available, max_per_day=1, min_per_day=1):
    """
    Using the available input variables, divide the list of seeded teams into
    the appropriate number of pools. Produce suitable draw formats definitions
    to execute the tournament.

    :param seeded_team_list: list of teams ordered by seeding rank
    :type seeded_team_list: int
    :param days_available: number of days available for play
    :type days_available: int
    :param max_per_day: max number of games a team may play in one day
    :type max_per_day: int
    :param min_per_day: min number of prelim games a team must play in one day
    :type min_per_day: int
    :returns: pools (list of lists) and draw_formats (list of dicts)
    :rtype: dict
    """
    number_of_teams = len(seeded_team_list)
    number_of_pools = optimum_tournament_pool_count(
        number_of_teams,
        days_available,
        max_per_day,
        min_per_day,
    )

    if isinstance(first(seeded_team_list), str):

        @functools.total_ordering
        class Team(object):
            def __init__(self, st, order):
                self.st = st
                self.order = order

            def __eq__(self, other):
                return self.order == other.order

            def __ne__(self, other):
                return not (self == other)

            def __lt__(self, other):
                return self.order < other.order

            def __str__(self):
                return self.st

            def __repr__(self):
                return "<Team: {} ({})>".format(self.st, self.order)

        seeded_team_list = [
            Team(t, order=order) for order, t in enumerate(seeded_team_list, 1)
        ]

    if number_of_pools is None:
        raise ValueError("Incompatible set of constraints")

    # split teams into number of pools, employing the "serpent" pattern
    pools = sorted(
        zip(
            *[
                g if i % 2 else reversed(g)
                for i, g in enumerate(grouper(seeded_team_list, number_of_pools))
            ]
        ),
        key=None,
    )

    # remove any None items from each pool
    pools = [[p for p in pool if p] for pool in pools]

    # produce round robin formats
    draw_formats = [
        {
            "label": "Round Robin (%d/%d teams)" % (size - 1, size),
            "format": round_robin_format(range(1, size + 1)),
        }
        # unique set of pool sizes requiring individual draw formats
        for size in sorted(
            set([int(ceiling(size, 2)) for size in [len(pool) for pool in pools]])
        )
    ]

    # produce finals formats
    draw_formats += [
        {
            "label": _("Final Series (%s pools)") % number_of_pools,
            "format": single_elimination_final_format(
                number_of_pools,
                bronze_playoff=_("Bronze Medal"),
            ),
        }
    ]

    return dict(pools=pools, draw_formats=draw_formats)
