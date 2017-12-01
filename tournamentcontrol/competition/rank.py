# -*- coding: utf-8 -*-

import logging
from datetime import datetime
from decimal import Decimal

import numpy
from dateutil.parser import parse as date_parse
from dateutil.relativedelta import relativedelta
from django.core.serializers import get_serializer
from django.db.models import Case, DecimalField, ExpressionWrapper, F, Q, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.module_loading import import_string
from django.views.generic import dates
from tournamentcontrol.competition.models import (
    LadderEntry, RankDivision, RankPoints, RankTeam,
)

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
            .order_by('team__division')
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


class TeamView(DivisionView):
    template_name_suffix = '_team'

    def get_context_data(self, **kwargs):
        data = super(TeamView, self).get_context_data(**kwargs)

        decay = import_string(self.kwargs.get(
            'decay', 'tournamentcontrol.competition.rank.no_decay'))
        version = "%(year)s-%(month)s-%(day)s" % self.kwargs
        at = date_parse(version).date()

        division = data['object']
        team = division.rankteam_set.get(club__slug=self.kwargs['team'])

        # Transform the data for template consumption.
        rows = [
            (each.match, each.rank_points, each.rank_points * decay(each, at=at))
            for each in LadderEntry.objects.filter(
                bye=0,
                division=division.pk,
                team__club__slug=self.kwargs['team'])
        ]

        # Punch this into the context to display in the front end.
        data['team'] = team
        data['table'] = rows
        data['points'] = numpy.mean([
            points_decay
            for match, points, points_decay in rows
        ])

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


def correct_points_func(win=15.0, draw=10.0, loss=5.0, forfeit_against=-20.0):
    "This version resolves the bug from the original implementation."
    return ExpressionWrapper(
        F('win') * win +
        F('draw') * draw +
        F('loss') * loss +
        F('forfeit_against') * forfeit_against +
        Case(
            When(Q(win=1, margin__gt=15), then=win * 2),
            When(Q(win=1, margin__gt=10), then=win),
            When(Q(win=1, margin__gt=5), then=win * 0.5),
            When(Q(loss=1, margin__lt=2), then=loss * 0.5),
            default=0,
        ),
        output_field=DecimalField(),
    )


def points_func(win=15.0, draw=10.0, loss=5.0, forfeit_against=-20.0):
    "This version preserves the bug from the original implementation."
    return ExpressionWrapper(
        F('win') * win +
        F('draw') * draw +
        F('loss') * loss +
        F('forfeit_against') * forfeit_against +
        # The original implementation did not choose one of these, it applied
        # all that were true. For the winning bonuses this meant a massive
        # accumulator for blowout scores (1.5 times greater than was intended).
        Case(
            When(Q(win=1, margin__gt=15), then=win * 3.5),
            When(Q(win=1, margin__gt=10), then=win * 1.5),
            When(Q(win=1, margin__gt=5), then=win * 0.5),
            When(Q(loss=1, margin__lt=2), then=loss * 0.5),
            default=0,
        ),
        output_field=DecimalField(),
    )


def no_decay(ladder_entry, at):
    return Constants.ONE


def _rank(decay=no_decay, start=None, at=None, **kwargs):
    if start is None:
        start = LadderEntry.objects.earliest('match').match.date

    if at is None:
        at = timezone.now() + relativedelta(day=1)

    if isinstance(at, datetime):
        at = at.date()

    ladder_entry_q = Q(match__date__gte=start, match__date__lt=at,
                       forfeit_for=0, importance__isnull=False, division__isnull=False)
    ladder_entries = LadderEntry.objects.select_related(
        'match__stage__division__season__competition').order_by('match')

    table = {}

    for ladder_entry in ladder_entries.filter(ladder_entry_q):
        obj, __ = RankTeam.objects.get_or_create(club=ladder_entry.team.club, division=ladder_entry.division)
        points = ladder_entry.rank_points * ladder_entry.importance
        points_decay = points * decay(ladder_entry, at)
        if points_decay:
            team = table.setdefault(obj.division, {}).setdefault(obj, {})
            team.setdefault('importance', []).append(ladder_entry.importance)
            team.setdefault('points', []).append(points)
            team.setdefault('points_decay', []).append(points_decay)
            team.setdefault('matches', []).append(ladder_entry.match)

    return table


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
    table = _rank(decay=decay, start=start, at=at, debug=debug)

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
