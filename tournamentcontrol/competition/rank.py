# -*- coding: utf-8 -*-

import logging
import re
from datetime import datetime
from decimal import Decimal

import numpy
from dateutil.relativedelta import relativedelta
from django.core.serializers import get_serializer
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import dates

from tournamentcontrol.competition.models import LadderEntry, RankPoints, RankTeam, RankDivision

logger = logging.getLogger(__name__)


class NodeToContextMixin(object):

    def get_context_data(self, **kwargs):
        data = super(NodeToContextMixin, self).get_context_data(**kwargs)
        data['node'] = self.kwargs.get('node')
        return data


class IndexView(NodeToContextMixin, dates.ArchiveIndexView):
    model = RankPoints
    date_field = 'date'
    date_list_period = 'day'

    def get_date_list(self, *args, **kwargs):
        date_list = super(IndexView, self).get_date_list(*args, **kwargs)
        return date_list[:12]


class YearView(NodeToContextMixin, dates.YearArchiveView):
    model = RankPoints
    date_field = 'date'
    date_list_period = 'day'


class MonthView(NodeToContextMixin, dates.MonthArchiveView):
    model = RankPoints
    date_field = 'date'


class DayView(NodeToContextMixin, dates.DayArchiveView):
    model = RankPoints
    date_field = 'date'
    allow_future = True

    def get_context_data(self, **kwargs):
        data = super(DayView, self).get_context_data(**kwargs)
        division_list = (
            data['object_list']
            .values_list('team__division__title', 'team__division__slug')
            .distinct()
        )
        data['division_list'] = division_list
        return data


class DivisionView(NodeToContextMixin, dates.DayArchiveView):
    model = RankPoints
    date_field = 'date'
    template_name_suffix = '_detail'
    allow_future = True

    def get_queryset(self):
        queryset = super(DivisionView, self).get_queryset()
        slug = self.kwargs['slug']
        division_queryset = queryset.filter(team__division__slug=slug)
        return division_queryset.order_by('-points')

    def get_context_data(self, **kwargs):
        data = super(DivisionView, self).get_context_data(**kwargs)
        slug = self.kwargs['slug']
        data['object'] = get_object_or_404(RankDivision, slug=slug)
        return data


class Constants:
    ZERO = Decimal(0)
    ONE = Decimal(1)

    HALF = ONE / 2
    QUARTER = ONE / 4
    FIFTH = ONE / 5
    SIXTH = ONE / 6
    SEVENTH = ONE / 7
    EIGHTH = ONE / 8


def base(ladder_entry, win=15, draw=10, loss=5, forfeit_against=-20):
    return sum([
        ladder_entry.win * win,
        ladder_entry.draw * draw,
        ladder_entry.loss * loss,
        ladder_entry.forfeit_against * forfeit_against,
        win * 2 if ladder_entry.win and ladder_entry.margin > 15 else 0,
        win if ladder_entry.win and ladder_entry.margin > 10 else 0,
        win * Constants.HALF if ladder_entry.win and ladder_entry.margin > 5 else 0,
        loss * Constants.HALF if ladder_entry.loss and ladder_entry.margin < 2 else 0,
    ])


def no_decay(ladder_entry, at):
    return Constants.ONE


def rank(decay=no_decay, start=None, at=None, debug=None):
    """
    Return an `OrderedDict` of key values, where the key is a `RankDivision`
    and the value is a nested `OrderedDict` of weighted scores, keyed by a
    `RankTeam`.

    The optional `decay` callable is used to determine the amount of decay that
    is to be weighted on the contribution of an individual result. Default is
    to apply no decay.

    The optional `start` date specifies the earliest matches to be considered
    in establishing a ranking score. The default is to include all available
    matches.

    The optional `at` date specifies the point in time at which the rank is to
    be calculated. This will both allow for retrospectives (what was the rank
    on a certain date in the past) and what will the current rank decay to in
    the future (exclusive of any results that will occur in the interim). The
    default is "tomorrow" if not specified.

    Pass a regex club names to `debug` and any
    `competition.LadderEntry.team.club.title` that matches will emit some DEBUG
    level log messages about those entries.

    :param decay:
    :param start:
    :param at:
    :param debug:
    :return:
    """
    if start is None:
        start = LadderEntry.objects.earliest('match').match.date

    if at is None:
        at = timezone.now() + relativedelta(day=1)

    if isinstance(at, datetime):
        at = at.date()

    if debug is None:
        debug = r'^$'
    debug_re = re.compile(debug, re.I)

    ladder_entry_q = Q(match__date__gte=start, match__date__lt=at,
                       forfeit_for=0)
    ladder_entries = LadderEntry.objects.select_related(
        'match__stage__division__season__competition').order_by('match')

    table = {}
    for ladder_entry in ladder_entries.filter(ladder_entry_q):
        importance = ladder_entry.match.get_rank_importance()
        division = ladder_entry.team.get_rank_division()
        if importance is None or division is None:
            continue
        obj, __ = RankTeam.objects.get_or_create(club=ladder_entry.team.club, division=division)
        points = base(ladder_entry) * importance
        points_decay = points * decay(ladder_entry, at)
        if points_decay:
            team = table.setdefault(division, {}).setdefault(obj, {})
            team.setdefault('importance', []).append(importance)
            team.setdefault('points', []).append(points)
            team.setdefault('points_decay', []).append(points_decay)
            if debug_re.match(obj.club.title):
                logger.debug(
                    u'%r\t%-20s\t%-20s\twin=%s\tmargin=%s\t%s → %s\t%s',
                    ladder_entry.match,
                    ladder_entry.team,
                    ladder_entry.opponent,
                    ladder_entry.win,
                    ladder_entry.margin,
                    points,
                    points_decay,
                    importance)

    RankPoints.objects.filter(date__year=at.year, date__month=at.month).delete()

    for division in table:
        for team in table[division]:
            RankPoints.objects.create(
                team=team,
                points=numpy.mean(table[division][team]['points_decay']),
                date=at)

    return RankPoints.objects.filter(date=at)


def json_rank(stream=None, indent=4, *args, **kwargs):
    JSONSerializer = get_serializer('json')
    json_serializer = JSONSerializer()
    json_serializer.serialize(
        rank(*args, **kwargs),
        stream=stream,
        indent=indent,
        use_natural_foreign_keys=True,
        use_natural_primary_keys=True)
