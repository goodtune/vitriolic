# -*- coding: utf-8 -*-

import logging
from datetime import datetime
from decimal import Decimal
from statistics import StatisticsError, mean

import django
from dateutil.parser import parse as date_parse
from dateutil.relativedelta import relativedelta
from django.core.serializers import get_serializer
from django.db.models import Case, ExpressionWrapper, F, FloatField, Q, When
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.module_loading import import_string
from django.views.generic import dates

from tournamentcontrol.competition.models import (
    LadderEntry,
    RankDivision,
    RankPoints,
    RankTeam,
)

logger = logging.getLogger(__name__)

OUTPUT_FIELD = FloatField() if django.VERSION[:2] >= (3, 2) else None

# Filter to determine which LadderEntry records get a rank_points attribute.
RANK_POINTS_Q = Q(match__is_bye=False, match__is_forfeit=False) | (
    (Q(match__is_forfeit=True) & ~Q(match__forfeit_winner=F("team")))
    & Q(division=F("opponent_division"))
)


class NodeToContextMixin(object):
    def get_context_data(self, **kwargs):
        data = super(NodeToContextMixin, self).get_context_data(**kwargs)
        data["node"] = self.kwargs.get("node")
        return data


class IndexView(NodeToContextMixin, dates.ArchiveIndexView):
    model = RankPoints
    date_field = "date"
    date_list_period = "day"

    def get_date_list(self, *args, **kwargs):
        date_list = super(IndexView, self).get_date_list(*args, **kwargs)
        return date_list[:12]


class YearView(NodeToContextMixin, dates.YearArchiveView):
    model = RankPoints
    date_field = "date"
    date_list_period = "day"


class MonthView(NodeToContextMixin, dates.MonthArchiveView):
    model = RankPoints
    date_field = "date"


class DayView(NodeToContextMixin, dates.DayArchiveView):
    model = RankPoints
    date_field = "date"
    allow_future = True

    def get_context_data(self, **kwargs):
        data = super(DayView, self).get_context_data(**kwargs)
        division_list = (
            data["object_list"]
            .order_by("team__division")
            .values_list("team__division__title", "team__division__slug")
            .distinct()
        )
        data["division_list"] = division_list
        return data


class DivisionView(NodeToContextMixin, dates.DayArchiveView):
    model = RankPoints
    date_field = "date"
    template_name_suffix = "_detail"
    allow_future = True

    def get_queryset(self):
        queryset = super(DivisionView, self).get_queryset()
        slug = self.kwargs["slug"]
        division_queryset = queryset.filter(team__division__slug=slug).select_related(
            "team__club"
        )
        return division_queryset.order_by("-points")

    def get_context_data(self, **kwargs):
        data = super(DivisionView, self).get_context_data(**kwargs)
        slug = self.kwargs["slug"]
        data["object"] = get_object_or_404(RankDivision, slug=slug)
        return data


class TeamView(DivisionView):
    template_name_suffix = "_team"

    def get_context_data(self, **kwargs):
        slug = self.kwargs["team"]
        data = super(TeamView, self).get_context_data(**kwargs)

        decay = import_string(
            self.kwargs.get("decay", "tournamentcontrol.competition.rank.no_decay")
        )
        version = "%(year)s-%(month)s-%(day)s" % self.kwargs
        at = date_parse(version).date()

        division = data["object"]
        team = get_object_or_404(division.rankteam_set, club__slug=slug)

        # Transform the data for template consumption.
        queryset = (
            LadderEntry.objects.filter(
                bye=0,
                division=division.pk,
                opponent_division=division.pk,
                team__club__slug=slug,
                match__date__lt=at,
            )
            .select_related(
                "match",
                "match__stage",
                "match__stage__division",
                "match__stage__division__season",
                "match__stage__division__season__competition",
                "match__home_team__club",
                "match__home_team__rank_division",
                "match__home_team__division__rank_division",
                "match__away_team__club",
                "match__away_team__rank_division",
                "match__away_team__division__rank_division",
            )
            # It would be nicer to use only but it's very easy to introduce breaking
            # changes. Let's defer useless and expensive columns we can easily identify.
            .defer(
                "match__away_team__club__short_title",
                "match__away_team_eval",
                "match__away_team_eval_related",
                "match__away_team_undecided",
                "match__bye_processed",
                "match__evaluated",
                "match__external_identifier",
                "match__home_team__club__short_title",
                "match__home_team_eval",
                "match__home_team_eval_related",
                "match__home_team_undecided",
                "match__include_in_ladder",
                "match__is_bye",
                "match__is_washout",
                "match__play_at",
                "match__round",
                "match__time",
                "match__videos",
                # This is a text field and could be quite large, we don't want to
                # return it for every match. We'll have a limited number of matches
                # to constrain the issue, but we have seen it bite before in real
                # world so let's defer it.
                "match__stage__division__season__competition__copy",
            )
            .order_by("match__datetime")
        )

        table = [
            (each.match, each.rank_points, each.rank_points * decay(each, at=at))
            for each in queryset
            if each.rank_points is not None
        ]

        series = [points_decay for match, points, points_decay in table]

        try:
            points = mean(series)
        except StatisticsError as exc:
            raise Http404(exc)

        # Punch this into the context to display in the front end.
        data["team"] = team
        data["table"] = table
        data["points"] = points

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
    return sum(
        [
            ladder_entry.win * win,
            ladder_entry.draw * draw,
            ladder_entry.loss * loss,
            ladder_entry.forfeit_against * forfeit_against,
            win * 2 if ladder_entry.win and ladder_entry.margin > 15 else 0,
            win if ladder_entry.win and ladder_entry.margin > 10 else 0,
            win * Constants.HALF if ladder_entry.win and ladder_entry.margin > 5 else 0,
            loss * Constants.HALF
            if ladder_entry.loss and ladder_entry.margin < 2
            else 0,
        ]
    )


def correct_points_func(win=15.0, draw=10.0, loss=5.0, forfeit_against=-20.0):
    "This version resolves the bug from the original implementation."
    expr = (
        F("win") * win
        + F("draw") * draw
        + F("loss") * loss
        + F("forfeit_against") * forfeit_against
        + Case(
            When(Q(win=1, margin__gt=15), then=win * 2),
            When(Q(win=1, margin__gt=10), then=win),
            When(Q(win=1, margin__gt=5), then=win * 0.5),
            When(Q(loss=1, margin__lt=2), then=loss * 0.5),
            default=0,
            output_field=OUTPUT_FIELD,
        )
    )
    return ExpressionWrapper(
        Case(When(RANK_POINTS_Q, then=expr), default=None), output_field=FloatField()
    )


def points_func(win=15.0, draw=10.0, loss=5.0, forfeit_against=-20.0):
    "This version preserves the bug from the original implementation."
    expr = (
        F("win") * win
        + F("draw") * draw
        + F("loss") * loss
        + F("forfeit_against") * forfeit_against
        +
        # The original implementation did not choose one of these, it applied
        # all that were true. For the winning bonuses this meant a massive
        # accumulator for blowout scores (1.5 times greater than was intended).
        Case(
            When(Q(win=1, margin__gt=15), then=win * 3.5),
            When(Q(win=1, margin__gt=10), then=win * 1.5),
            When(Q(win=1, margin__gt=5), then=win * 0.5),
            When(Q(loss=1, margin__lt=2), then=loss * 0.5),
            default=0,
            output_field=OUTPUT_FIELD,
        )
    )
    return ExpressionWrapper(
        Case(When(RANK_POINTS_Q, then=expr), default=None), output_field=FloatField()
    )


def no_decay(ladder_entry, at):
    return Constants.ONE


def _rank(decay=no_decay, start=None, at=None, **kwargs):
    if start is None:
        start = LadderEntry.objects.earliest("match").match.date

    if at is None:
        at = timezone.now() + relativedelta(day=1)

    if isinstance(at, datetime):
        at = at.date()

    ladder_entry_q = Q(
        match__date__gte=start,
        match__date__lt=at,
        forfeit_for=0,
        importance__isnull=False,
        division__isnull=False,
        division=F("opponent_division"),
    )
    ladder_entries = LadderEntry.objects.select_related(
        "match__stage__division__season__competition"
    ).order_by("match")

    table = {}

    # For performance, use in_bulk to create a dictionary mapping each
    # RankDivision with pk as it the dictionary key, and model instance
    # as the value.
    rank_divisions = RankDivision.objects.in_bulk()

    for ladder_entry in ladder_entries.filter(ladder_entry_q):
        if ladder_entry.rank_points is None:
            continue
        obj, __ = RankTeam.objects.get_or_create(
            club=ladder_entry.team.club, division=rank_divisions[ladder_entry.division]
        )
        points = ladder_entry.rank_points
        points_decay = points * decay(ladder_entry, at)
        if points_decay:
            team = table.setdefault(obj.division, {}).setdefault(obj, {})
            team.setdefault("importance", []).append(ladder_entry.importance)
            team.setdefault("points", []).append(points)
            team.setdefault("points_decay", []).append(points_decay)
            team.setdefault("matches", []).append(ladder_entry.match)

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
                points=mean(table[division][team]["points_decay"]),
                date=at,
            )

    return RankPoints.objects.filter(date=at)


def json_rank(stream=None, indent=4, *args, **kwargs):
    JSONSerializer = get_serializer("json")
    json_serializer = JSONSerializer()
    json_serializer.serialize(
        rank(*args, **kwargs),
        stream=stream,
        indent=indent,
        use_natural_foreign_keys=True,
        use_natural_primary_keys=True,
    )
