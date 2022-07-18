from __future__ import unicode_literals

import datetime
import functools
import itertools
import logging
import re
from collections import defaultdict
from decimal import Decimal
from typing import Optional

from dateutil.rrule import DAILY, WEEKLY, rrule, rruleset
from django.conf import settings
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from first import first

from tournamentcontrol.competition.models import (
    Match,
    Stage,
    StageGroup,
    Team,
    UndecidedTeam,
)
from tournamentcontrol.competition.utils import (
    ceiling,
    final_series_rounds,
    grouper,
    round_robin_format,
    single_elimination_final_format,
)

win_lose_re = re.compile(r"(?P<result>[WL])(?P<match_id>\d+)")

logger = logging.getLogger(__name__)


def coerce_datetime(start_date):
    """
    When operating with time zone aware objects we're better off converting
    our plain old date instances to datetime instances before handing them
    to the rruleset.

    If USE_TZ is True and the datetime isn't aware (it may have been passed
    in as an aware datetime) then also set the time zone to UTC.
    """
    if isinstance(start_date, datetime.date):
        start_date = datetime.datetime.combine(start_date, datetime.time())
    if settings.USE_TZ:
        if not timezone.is_aware(start_date):
            start_date = timezone.make_aware(
                start_date, timezone.get_current_timezone()
            )
    return start_date


def weekly_date_generator(stage, start_date=None):
    if start_date is None:
        start_date = stage.division.season.start_date
    start_date = coerce_datetime(start_date)
    logger.debug("Weekly date generator: '%s' (%s)", stage.title, start_date)
    ruleset = rruleset()
    ruleset.rrule(rrule(WEEKLY, dtstart=start_date))
    for exclusion in stage.division.season.exclusions.dates("date", "day"):
        exclusion = coerce_datetime(exclusion)
        ruleset.exdate(exclusion)
        logger.debug("EXCLUSION (%s) %s", stage.division.season.title, exclusion)
    for exclusion in stage.division.exclusions.dates("date", "day"):
        exclusion = coerce_datetime(exclusion)
        ruleset.exdate(exclusion)
        logger.debug("EXCLUSION (%s) %s", stage.division.title, exclusion)
    return iter(ruleset)


def tournament_date_generator(stage, start_date=None, games_per_day=None):
    if start_date is None:
        start_date = stage.division.season.start_date
    start_date = coerce_datetime(start_date)

    if games_per_day is None:
        # in case `games_per_day` is not set on the division, fallback to 1
        games_per_day = stage.division.games_per_day or 1

    logger.debug(
        "Tournament date generator: '%s' (%s:%s)",
        stage.title,
        start_date,
        games_per_day,
    )

    ruleset = rruleset()
    ruleset.rrule(rrule(DAILY, dtstart=start_date))

    for exclusion in stage.division.season.exclusions.dates("date", "day"):
        exclusion = coerce_datetime(exclusion)
        ruleset.exdate(exclusion)
        logger.debug("EXCLUSION (%s) %s", stage.division.season.title, exclusion)

    for exclusion in stage.division.exclusions.dates("date", "day"):
        exclusion = coerce_datetime(exclusion)
        ruleset.exdate(exclusion)
        logger.debug("EXCLUSION (%s) %s", stage.division.title, exclusion)

    for dates in map(lambda dt: itertools.repeat(dt.date(), games_per_day), ruleset):
        for date in dates:
            yield date


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
            logger.warn(
                "Too many games (%s) to be played before the finals " "with %s pools.",
                preliminary_rounds,
                number_of_pools,
            )
            continue

        # Make sure we are playing enough games during the preliminary stages
        if preliminary_rounds / max_per_day > days_available - elimination_days:
            logger.warn(
                "Not enough time (%s days) to play %s games at %s " "games per day.",
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


class RoundDescriptor(object):
    def __init__(self, count, round_label, **kwargs):
        self.count = count
        self.round_label = round_label
        self.matches = []

    def add(self, match):
        self.matches.append(match)

    def generate(self, generator, stage, date):
        return [m.generate(generator, stage, self, date) for m in self.matches]

    def __str__(self):
        return "\n".join(
            ["ROUND %s" % self.round_label] + [str(m) for m in self.matches]
        )


class MatchDescriptor(object):
    def __init__(self, match_id, home_team, away_team, match_label=None, **kwargs):
        self.match_id = match_id
        self.home_team = home_team
        self.away_team = away_team
        self.match_label = match_label

    def __str__(self):
        if self.match_label:
            return '%s: %s vs %s "%s"' % (
                self.match_id,
                self.home_team,
                self.away_team,
                self.match_label,
            )
        return "%s: %s vs %s" % (self.match_id, self.home_team, self.away_team)

    def generate(self, generator, stage, round, date):
        if isinstance(stage, StageGroup):
            stages = {
                "stage": stage.stage,
                "stage_group": stage,
            }
            include_in_ladder = stage.stage.keep_ladder
        else:
            stages = {"stage": stage}
            include_in_ladder = stage.keep_ladder

        match = Match(
            label=self.match_label or round.round_label,
            include_in_ladder=include_in_ladder,
            round=round.count,
            date=date,
            **stages,
        )

        setattr(match, "descriptor", self)

        home_team = generator.team(self.home_team)
        away_team = generator.team(self.away_team)

        if home_team is None:
            match.is_bye = True
        elif isinstance(home_team, UndecidedTeam):
            match.home_team_undecided = home_team
        elif isinstance(home_team, Team):
            match.home_team = home_team
        else:
            match.home_team_eval = home_team

        if away_team is None:
            match.is_bye = True
        elif isinstance(away_team, UndecidedTeam):
            match.away_team_undecided = away_team
        elif isinstance(away_team, Team):
            match.away_team = away_team
        else:
            match.away_team_eval = away_team

        if match.home_team_eval or match.away_team_eval:
            match.evaluated = False

        return (self.match_id, match)


class MatchCollection(object):
    def __init__(self):
        self.keyed = {}
        self.iterable = []
        # QuerySet faking attributes
        self.ordered = True
        # self.db = 'default'

    def __add__(self, other):
        for key, value in other.keyed.items():
            self.keyed[key] = value
        self.iterable += other.iterable
        self.iterable.sort(key=lambda m: m.date)
        return self

    def __getitem__(self, key):
        try:
            return self.keyed[key]
        except KeyError:
            return self.iterable[key]

    def __iter__(self, *args, **kwargs):
        return iter(self.iterable)

    def __len__(self):
        return len(self.iterable)

    def __repr__(self):
        return repr(self.iterable)

    def add(self, match_id, match):
        self.keyed.setdefault(match_id, []).append(match)
        self.iterable.append(match)

    def get(self, match_id):
        return self.keyed.get(match_id)

    def get_latest(self, match_id, **kwargs):
        return self.get(match_id)[-1]

    def save(self):
        for match in self.iterable:
            # I'm unsure if this is a Django related bug, but when I think it
            # might related to a database optimisation - see
            # djangoproject:#6886 - to prevent a hit when you've just assigned.
            #
            # To fix our case, simply re-assign the cached object back so that
            # we update the id field before our database INSERT.
            if match.home_team_eval_related:
                match.home_team_eval_related = match.home_team_eval_related
            if match.away_team_eval_related:
                match.away_team_eval_related = match.away_team_eval_related
            match.save()


class DrawGenerator(object):
    regex = re.compile(
        r"""  # noqa
        (?:
            (?P<round>ROUND(?:\ +(?P<round_label>\d+|[\S ]+))?)         # Start a new Round section
        )

        |                                                               # OR

        (?:
            (?P<match_id>\d+):\s*                                       # match ID (with whitespace)
            (?P<home_team>(?:(?:S\d+)?(?:(?:G\d+)?P|[WL])|[PWL])?\d+)   # home team ID
            \s*vs\s*                                                    # versus literal (with whitespace)
            (?P<away_team>(?:(?:S\d+)?(?:(?:G\d+)?P|[WL])|[PWL])?\d+)   # away team ID
            \ *(?P<match_label>[\S ]+)?                                 # match label (optional)
        )
        """,
        re.VERBOSE,
    )

    def __init__(self, stage: Stage, start_date: Optional[datetime.date] = None):
        self.rounds = []
        self.stage = stage
        self.start_date = start_date
        self.teams = defaultdict(lambda: None)
        if isinstance(stage, Stage):
            if stage.order > 1:
                queryset = stage.undecided_teams.all()
            else:
                queryset = stage.division.teams.all()
            teams = dict(enumerate(queryset))
        elif isinstance(stage, StageGroup):
            if stage.stage.order > 1:
                queryset = stage.undecided_teams.all()
            else:
                queryset = stage.teams.all()
            teams = dict(enumerate(queryset))
        self.teams.update(teams)

    def team(self, text):
        if text.isdigit():
            return self.teams[int(text) - 1]
        return text

    def parse(self, text):
        round = None
        count = 1

        for line in self.regex.finditer(text):
            data = line.groupdict()

            if data.get("round"):
                round = RoundDescriptor(count=count, **data)
                self.rounds.append(round)
                count += 1
                continue

            match = MatchDescriptor(**data)
            round.add(match)

    def generate(self, n=None, offset=0):
        # if n is not specified generate one complete round
        if n is None:
            n = len(self.rounds)

        rounds = itertools.cycle(self.rounds)

        if self.stage.division.season.mode == WEEKLY:
            logger.debug(
                "WEEKLY generator mode: '%s' (%s)", self.stage.title, self.start_date
            )
            dates = weekly_date_generator(self.stage, self.start_date)
        elif self.stage.division.season.mode == DAILY:
            logger.debug(
                "DAILY generator mode: '%s' (%s)", self.stage.title, self.start_date
            )
            dates = tournament_date_generator(self.stage, self.start_date)
        else:
            logger.debug(
                "Fallback date generator [%s]: '%s' (%s)",
                self.stage.division.season.mode,
                self.stage.title,
                self.start_date,
            )
            dates = itertools.cycle([None])

        matches = MatchCollection()

        # Work out what stage we come after, could be with reference to a
        # Stage or a StageGroup so introspect the type.
        try:
            initial = 1
            if isinstance(self.stage, Stage):
                follows = self.stage.comes_after
            elif isinstance(self.stage, StageGroup):
                follows = self.stage.stage.comes_after
        except Stage.DoesNotExist:
            pass
        else:
            # Set our initial round number, if we're following another stage,
            # keep the number ticking over from that point.
            if follows is not None:
                initial += follows.matches.aggregate(max=Max("round")).get("max") or 0

        for i in range(offset + initial, offset + n + initial):
            date = next(dates)
            round = next(rounds)
            for match_id, match in round.generate(self, self.stage, date):
                match.round = i
                matches.add(match_id, match)

                # update the related match values and store only the W or L
                for team in ("home", "away"):
                    team_eval = win_lose_re.match(
                        getattr(match, f"{team}_team_eval") or ""
                    )
                    if team_eval:
                        decode = team_eval.groupdict()
                        setattr(
                            match,
                            f"{team}_team_eval_related",
                            matches.get_latest(**decode),
                        )
                        setattr(match, f"{team}_team_eval", decode.get("result"))

        return matches

    @classmethod
    def validate(cls, text):
        errors = set()
        keys = set()
        for line, data in enumerate(text.splitlines()):
            match = cls.regex.match(data)
            if not match:
                errors.add(line)
                continue
            match_id = match.groupdict().get("match_id")
            if match_id:
                if match_id in keys:
                    errors.add(line)
                keys.add(match_id)
        if errors:
            raise ValueError(
                "Draw formula is invalid: line(s) '%s' are not "
                "in the correct format." % ", ".join([str(e) for e in errors])
            )
        return True
