"""The day segment of an ops URL: ``YYYYMMDD`` in the season's calendar."""

import datetime

from django.http import Http404


def parse_day(datestr):
    try:
        return datetime.datetime.strptime(datestr, "%Y%m%d").date()
    except ValueError:
        raise Http404("Invalid date.")


def day_kwargs(season, day):
    return {
        "competition": season.competition.slug,
        "season": season.slug,
        "datestr": day.strftime("%Y%m%d"),
    }
