import collections
import logging
import re
from datetime import datetime
from decimal import Decimal
from operator import and_, attrgetter, or_

import pytz
import six
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import F, Q
from django.http import HttpResponse
from django.template.loader import select_template
from django.utils import timezone
from touchtechnology.common.prince import prince

try:
    from itertools import zip_longest
except ImportError:
    from itertools import izip_longest as zip_longest


logger = logging.getLogger(__name__)

home_team_needs_progressing = and_(Q(home_team__isnull=True),
                                   or_(Q(home_team_undecided__isnull=False),
                                       Q(home_team_eval__isnull=False)))

away_team_needs_progressing = and_(Q(away_team__isnull=True),
                                   or_(Q(away_team_undecided__isnull=False),
                                       Q(away_team_eval__isnull=False)))

team_needs_progressing = and_(or_(home_team_needs_progressing,
                                  away_team_needs_progressing),
                              Q(stage__division__season__complete=False))

legitimate_bye_match = and_(Q(is_bye=True),
                            or_(Q(home_team__isnull=False),
                                Q(away_team__isnull=False)))

match_unplayed = or_(Q(home_team_score__isnull=True),
                     Q(away_team_score__isnull=True))

stage_group_position_re = re.compile(
    r'''
    (?:
        S(?P<stage>\d+)         # stage number (optional)
    )?
    (?:
        G(?P<group>\d+)         # group number (optional)
    )?
    P(?P<position>\d+)          # position number
    ''',
    re.VERBOSE,
)


class FauxQueryset(list):
    """
    In some scenarios we need to construct a list-like object so we
    can handle the ordering of the objects.
    """
    def __init__(self, model, team=None, *args, **kwargs):
        super(FauxQueryset, self).__init__(*args, **kwargs)
        # the team attribute is a legacy from a previous implementation
        # detail, we need to improve this. FIXME.
        self.team = team
        self.model = model
        self.ordered = True
        self.db = None
        self._prefetch_related_lookups = True  # ModelChoiceIterator

    def all(self):
        return self

    def get(self, **kwargs):
        pks = map(attrgetter('pk'), self)
        return self.model.objects.filter(pk__in=pks).get(**kwargs)


class SumDict(dict):
    """
    When calculating the values for a LadderSummary we may need to
    quickly add together aggregated values. These will already be
    accessible as a `dict` so this will quickly allow us to add the
    values together and get a total.
    """
    def __add__(self, other):
        i = {}
        for d in (self, other):
            for k, v in d.items():
                i.setdefault(k, []).append(v if v is not None else 0)
        return SumDict([(k, sum(v)) for k, v in i.items()])


#
# Mathematical
#


def ceiling(value, factor=1):
    """
    For a Decimal value, round it up to the nearest multiple of ``factor``.

        >>> ceiling(3.5)
        Decimal('4')
        >>> ceiling(3.5, 0.75)
        Decimal('3.75')

    :param value: number to be rounded up
    :param factor: multiplier to round up to
    :return: Decimal
    """
    value = Decimal(str(value))
    factor = Decimal(str(factor))
    return (value / factor).quantize(1, rounding='ROUND_UP') * factor


def floor(value, factor=1):
    """
    For a Decimal value, round it down to the nearest multiple of ``factor``.

        >>> floor(3.5)
        Decimal('3')
        >>> floor(2.5, 0.6)
        Decimal('2.4')

    :param value: number to be rounded down
    :param factor: multiplier to round down to
    :return: Decimal
    """
    value = Decimal(str(value))
    factor = Decimal(str(factor))
    return (value / factor).quantize(1, rounding='ROUND_DOWN') * factor


def revpow(n, base):
    """
    Reverse of ``pow`` built-in function.

        >>> for i in range(4):
        ...     revpow(pow(2, i), 2) == i
        ...
        True
        True
        True
        True

    :param n: number that is a power of base
    :param base: the base
    :return: int
    """
    res = 0
    intermediate = n / base
    if intermediate:
        res += 1
        res += revpow(intermediate, base)
    return res


#
# Iterables
#


def grouper(iterable, size, fill=None):
    """
    Collect data into fixed-length chunks or blocks. Lifted from
    https://docs.python.org/2/library/itertools.html#recipes

        >>> list(grouper('ABCDEFG', 3, 'x'))
        [('A', 'B', 'C'), ('D', 'E', 'F'), ('G', 'x', 'x')]

    :param iterable: thing to be broken into chunks
    :param size: size of each chunk
    :param fill: value to use to pad chunks of less than size
    :return: zip_longest
    """
    args = [iter(iterable)] * size
    return zip_longest(fillvalue=fill, *args)


#
# Timeslots & timezones
#


def combine_and_localize(date, time, tz):
    """
    Given the date and time parts, return a timezone aware
    datetime instance. Date and time parts are considered
    local to tzinfo.
    """
    combined = datetime.combine(date, time)
    if isinstance(tz, six.string_types):
        tz = pytz.timezone(tz)
    return timezone.make_aware(combined, tz)


def time_choice(t):
    return (t.strftime("%H:%M:%S"), t.strftime("%H:%M"))


#
# Competition draw generation utilities
#


def round_robin(teams, rounds=None):
    """
    Based on recipe found at http://code.activestate.com/recipes/65200/
    """
    # ensure we have an even number of teams
    if len(teams) % 2:
        teams.append(0)

    count = len(teams)
    half = int(count / 2)

    # if the rounds is not set, we will produce one complete round
    if rounds is None:
        rounds = count - 1

    schedule = []
    for turn in range(rounds):
        pairings = []
        for i in range(half):
            pairings.append((teams[i], teams[count - i - 1]))
        teams.insert(1, teams.pop())
        schedule.append(pairings)

    return schedule


def round_robin_format(teams, rounds=None):
    i, s = 1, ""
    for round in round_robin(teams, rounds):
        s += 'ROUND\n'
        for home, away in round:
            s += '%s: %s vs %s\n' % (i, home, away)
            i += 1
    return s.strip()


def final_series_rounds(pools):
    """
    For a given number of pools determine the correct number of rounds to
    play in a final series to fairly determine a winner.

    :param pools: number of pools
    :return: int
    """
    rounds = revpow(pools, 2)
    if rounds <= 1:
        return 2
    return rounds + 1


def final_series_round_label(number_of_matches):
    if number_of_matches >= 8:
        return "Round of %d" % (number_of_matches * 2)
    if number_of_matches == 4:
        return "Quarter Final"
    if number_of_matches == 2:
        return "Semi Final"
    return "Final"


def single_elimination_final_format(number_of_pools, bronze_playoff=None):
    """
    For any number of pools, construct a single elimination draw format to
    find the champion team.

    :param number_of_pools: number of starting groups
    :param bronze_playoff: unicode label for 3rd place playoff. If None no
                           match will be scheduled.
    :return: list
    """
    from tournamentcontrol.competition.draw import (
        MatchDescriptor,
        RoundDescriptor,
    )

    # Start building our final series with the initial round. Each match is
    # ordered so that the pool from which the highest seeds were originally
    # placed (pool 1) are farthest away from the second highest seed (pool 2).
    # In effect, this means P1, P2, ... PN.

    if number_of_pools == 1:
        initial = RoundDescriptor(2, final_series_round_label(2))
        initial.add(MatchDescriptor(1, 'P1', 'P4'))
        initial.add(MatchDescriptor(2, 'P2', 'P3'))

    else:
        initial = RoundDescriptor(
            number_of_pools,
            final_series_round_label(number_of_pools))

        for pool in range(number_of_pools):
            match = MatchDescriptor(
                pool + 1,
                'G%dP1' % (pool + 1),
                'G%dP2' % (number_of_pools - pool),
            )
            initial.add(match)

    series = [
        initial,
    ]

    # Until we reach the final round (we don't know how many hops yet),
    # introspect the previous round and add a match between plays the highest
    # remaining seed against the lowest remaining seed.
    # In effect, this means W1 vs W-1, W2 vs W-2, ...

    while len(series[-1].matches) > 1:
        # Always half as many as the previous round, we're eliminating teams!
        matches_this_round = len(series[-1].matches) / 2

        this_round = RoundDescriptor(
            matches_this_round,
            final_series_round_label(matches_this_round))

        for i in range(matches_this_round):
            match = MatchDescriptor(
                series[-1].matches[-1].match_id + i + 1,
                'W%s' % (series[-1].matches[i].match_id),
                'W%s' % (series[-1].matches[-1 - i].match_id),
            )
            this_round.add(match)

        series.append(this_round)

    # If we want to schedule a 3rd place playoff, add an extra match to the
    # final round we've already created.
    if bronze_playoff is not None:
        match = MatchDescriptor(
            series[-1].matches[0].match_id + 1,
            'L%s' % (series[-2].matches[0].match_id),
            'L%s' % (series[-2].matches[1].match_id),
            bronze_playoff,
        )
        series[-1].add(match)

        # Also update the match label of the only other match in this stage.
        series[-1].matches[0].match_label = series[-1].round_label

    return series


def stage_group_position(stage, formula):
    match = stage_group_position_re.match(formula)
    if not match:
        logger.exception("Formula %r is invalid", formula)
        raise ValueError("Invalid formula")

    s, g, p = match.groups()
    logger.debug("stage = %s, group = %s, position = %s", s, g, p)

    if s is None:
        logger.debug('No stage specified in formula %r', formula)
        s = stage.comes_after
    else:
        try:
            s = stage.division.stages.all()[int(s) - 1]
        except IndexError:
            logger.exception(
                'Invalid stage %r for division %r', s, stage.division)
            raise
    logger.debug('stage=%r', s)

    if g is None:
        logger.debug('No group specified in formula %r', formula)
    else:
        try:
            g = s.pools.all()[int(g) - 1]
        except IndexError:
            logger.exception('Invalid group %r for stage %r', g, stage)
            raise
    logger.debug('group=%r', g)

    p = int(p)
    logger.debug('position=%r', p)

    return s, g, p


#
# Scorecards
#


def generate_scorecards(matches=None, templates=None, format='html',
                        extra_context=None, stage=None, **kwargs):
    if extra_context is None:
        extra_context = {}

    context = {
        'matches': matches,
    }
    context.update(extra_context)

    template = select_template(templates)
    output = template.render(context)

    if format == 'pdf':
        output = prince(output, **kwargs)

    if stage is not None:
        for match in matches:
            match.to_be_printed.remove(stage)

    return output


def generate_fixture_grid(season, dates=None, templates=None,
                          format='html', request=None,
                          extra_context=None, **kwargs):
    if dates is None:
        dates = season.matches.dates('date', 'day')

    if templates is None:
        templates = ['tournamentcontrol/competition/admin/grid.html']

    if extra_context is None:
        extra_context = {}

    matrices = collections.OrderedDict()

    play_at = season.get_places()

    for date in dates:
        matches = season.matches.filter(date=date)

        times = set(matches.values_list('time', flat=True)).union(
            season.get_timeslots(date))
        times = sorted(filter(None, times))

        keyed = collections.defaultdict(lambda: None)
        for m in matches:
            keyed.setdefault((m.play_at, m.time), []).append(m)

        matrix = collections.OrderedDict()
        for t in times:
            matrix.setdefault(t, collections.OrderedDict())
            for p in play_at:
                matrix[t].setdefault(p, keyed[(p, t)])

        matrices.setdefault(date, matrix)

    context = {
        'matrices': matrices,
        'venues': season.venues.all(),
        'columns': play_at,
    }
    context.update(extra_context)

    template = select_template(templates)
    html = template.render(context)

    if format == 'pdf':
        pdf = prince(html, **kwargs)
        response = HttpResponse(pdf, content_type="application/pdf")
    else:
        response = HttpResponse(html)

    return response


#
# Forfeit handling
#

def forfeit_notification_recipients(match):
    """
    Return a 2-tuple of users to contact advising them that a forfeit
    notification has been received from team for match.

    The first element is a queryset of the affected players, while the second
    is the queryset of users attached to the matches season to be notified.

    This function does not send any notifications!
    """
    UserModel = get_user_model()

    people = match.forfeit_winner.people.exclude(person__user__isnull=True)
    user = UserModel.objects.filter(person__in=people.values('person'))

    return (user, match.stage.division.season.forfeit_notifications.all())


#
# regrade
#


def regrade(team, to, from_date=None):
    Division = apps.get_model('competition', 'Division')
    Team = apps.get_model('competition', 'Team')

    assert isinstance(team, Team), "team is not a Team instance"
    assert isinstance(to, Division), "to is not a Division instance"
    assert team.division != to, "move to same Division is not allowed"
    assert team.division.season == to.season, \
        "move to different Season is not allowed"

    # Work out the regrade date if not specified
    if from_date is None:
        from_date = team.matches.filter(match_unplayed).earliest('date').date

    # Update the sequence numbers of all teams in the current division to keep
    # them in order without any gaps
    team.division.teams.filter(order__gt=team.order) \
                       .update(order=F('order') - 1)

    # All unplayed matches that this team is assigned to play need to be turned
    # into byes, removing them from the home_team and away_team fields. Strip
    # the time and field also.
    old_matches = team.matches.filter(match_unplayed, date__gte=from_date)
    old_matches.filter(home_team=team).update(
        home_team=None, is_bye=True, time=None, datetime=None, play_at=None)
    old_matches.filter(away_team=team).update(
        away_team=None, is_bye=True, time=None, datetime=None, play_at=None)

    # Move team into the bye matches in the new division.
    new_matches = to.matches.filter(legitimate_bye_match, date__gte=from_date)
    new_matches.filter(home_team=None).update(home_team=team, is_bye=False)
    new_matches.filter(away_team=None).update(away_team=team, is_bye=False)

    # Determine the highest sequence value in the target division and assign
    # that to our team. If it throws an DoesNotExist exception, the division
    # is empty and we need to set it to 1.
    try:
        team.order = to.teams.latest('order').order + 1
    except Team.DoesNotExist:
        team.order = 1


#
# label_from_instance utilities
#

def team_and_division(o):
    "For use on Model.team_clashes as label_from_instance argument."
    return "%s (%s)" % (o.title, o.division.title)
