import datetime
import itertools
import logging
import re
from collections import defaultdict
from typing import Optional

from dateutil.rrule import DAILY, WEEKLY, rrule, rruleset
from django.db.models import Max

from tournamentcontrol.competition.draw.algorithms import coerce_datetime
from tournamentcontrol.competition.draw.schemas import (
    WIN_LOSE_RE,
    MatchDescriptor,
    RoundDescriptor,
)
from tournamentcontrol.competition.models import Stage, StageGroup

logger = logging.getLogger(__name__)


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
        return f"<MatchCollection: {self.iterable!r}>"

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
    """
    DrawGenerator parses tournament draw format strings and generates Match objects.

    DRAW FORMAT SYNTAX:

    The draw format uses a simple text-based syntax to describe tournament brackets:

    ROUND [optional_label]
    match_id: team1 vs team2 [optional_match_label]

    TEAM REFERENCES:
    - Direct indices: 1, 2, 3, 4 (refers to teams by their position in the division)
    - Winner references: W1, W2 (winner of match ID 1, 2)
    - Loser references: L1, L2 (loser of match ID 1, 2)
    - Pool position references: G1P1, G2P3 (Group 1 Position 1, Group 2 Position 3)
    - Stage references: S1G1P2 (Stage 1 Group 1 Position 2)

    EXAMPLES:

    Simple Knockout (4 teams):
    ```
    ROUND
    1: 1 vs 2 Semi 1
    2: 3 vs 4 Semi 2
    ROUND
    3: L1 vs L2 Bronze
    ROUND
    4: W1 vs W2 Final
    ```

    Round Robin (4 teams):
    ```
    ROUND
    1: 1 vs 2
    2: 3 vs 4
    ROUND
    3: 1 vs 3
    4: 2 vs 4
    ROUND
    5: 1 vs 4
    6: 2 vs 3
    ```

    Complex Multi-Stage with Pool References:
    ```
    ROUND
    1: G1P1 vs G1P2 Pool Winner Playoff
    2: G2P3 vs G2P4 Consolation
    ```

    The generator processes these formats and creates Match objects with proper
    team assignments and progression logic.
    """

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
        # Without a stage (previewing a format) there are no teams to map.
        teams = {}
        if isinstance(stage, Stage):
            if stage.order > 1:
                queryset = stage.undecided_teams.all()
            else:
                queryset = stage.division.teams.all()
            teams = dict(enumerate(self._stable(queryset)))
        elif isinstance(stage, StageGroup):
            if stage.stage.order > 1:
                queryset = stage.undecided_teams.all()
            else:
                queryset = stage.teams.all()
            teams = dict(enumerate(self._stable(queryset)))
        self.teams.update(teams)

    @staticmethod
    def _stable(queryset):
        """
        Numeric references are mapped to teams by their position in the
        queryset, so the order must be total for the same inputs to always
        produce the same draw: keep the model's ordering and break any tie
        on the primary key.
        """
        return queryset.order_by(*queryset.model._meta.ordering, "pk")

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

    def generate(
        self,
        n=None,
        offset=0,
        custom_date_generator=None,
        alternate_home_away_on_repeat=False,
    ):
        """
        Generate ``n`` rounds (default: one pass of the format), cycling
        through the format when ``n`` exceeds its length. With
        ``alternate_home_away_on_repeat`` every second pass through the
        format swaps the home and away sides of each match.
        """
        # if n is not specified generate one complete round
        if n is None:
            n = len(self.rounds)

        rounds = itertools.cycle(self.rounds)

        if custom_date_generator is not None:
            logger.debug(
                "CUSTOM generator mode: '%s' (%s)", self.stage.title, self.start_date
            )
            dates = custom_date_generator(self.stage, self.start_date)
        elif self.stage.division.season.mode == WEEKLY:
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

        for index, i in enumerate(range(offset + initial, offset + n + initial)):
            date = next(dates)
            round = next(rounds)
            swap = alternate_home_away_on_repeat and (index // len(self.rounds)) % 2
            for match_id, match in round.generate(self, self.stage, date):
                match.round = i
                if swap:
                    self._swap_home_away(match)
                matches.add(match_id, match)

                # update the related match values and store only the W or L
                for team in ("home", "away"):
                    team_eval = WIN_LOSE_RE.match(
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

    @staticmethod
    def _swap_home_away(match):
        for field in ("team", "team_undecided", "team_eval"):
            home, away = getattr(match, f"home_{field}"), getattr(
                match, f"away_{field}"
            )
            setattr(match, f"home_{field}", away)
            setattr(match, f"away_{field}", home)

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
