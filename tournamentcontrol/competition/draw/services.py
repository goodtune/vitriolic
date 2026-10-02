"""
Draw generation services shared by the admin site's Draw Generation wizard
(``DrawGenerationForm``), the division structure builder and the
administration MCP tools, so every way of building a draw from a
``DrawFormat`` produces the same matches from the same inputs.
"""

import datetime
from typing import Optional, Union

from django.db.models import Q
from first import first

from tournamentcontrol.competition.draw.generators import (
    DrawGenerator,
    MatchCollection,
)
from tournamentcontrol.competition.models import DrawFormat, Stage, StageGroup

DrawTarget = Union[Stage, StageGroup]


def draw_target_team_count(target: Optional[DrawTarget]) -> int:
    """
    The number of teams a draw for ``target`` is built for: the teams of a
    first stage or pool, otherwise the undecided teams waiting on an earlier
    stage (whichever is non-zero first, as the wizard has always counted).
    """
    if isinstance(target, Stage):
        return first((target.teams.count(), target.undecided_teams.count()), default=0)
    if isinstance(target, StageGroup):
        return first((target.undecided_teams.count(), target.teams.count()), default=0)
    return 0


def suitable_draw_formats(teams: int, queryset=None):
    """
    The draw formats suitable for ``teams`` teams: an odd number is rounded
    up (the extra team is a bye) and formats for that number or one fewer
    are offered. With no teams every format is suitable.
    """
    if queryset is None:
        queryset = DrawFormat.objects.all()
    if teams % 2:
        teams += 1
    return queryset.filter(Q(teams__in=(teams, teams - 1)) if teams else Q())


def draw_generator(
    target: Optional[DrawTarget],
    draw_format: Union[DrawFormat, str],
    start_date: Optional[datetime.date] = None,
) -> DrawGenerator:
    """
    A ``DrawGenerator`` for ``target`` with ``draw_format`` (a saved format
    or its raw text) parsed. ``target`` may be ``None`` to inspect a format
    without any teams.
    """
    text = draw_format.text if isinstance(draw_format, DrawFormat) else draw_format
    generator = DrawGenerator(target, start_date)
    generator.parse(text)
    return generator


def generate_stage_draw(
    target: DrawTarget,
    draw_format: Union[DrawFormat, str],
    start_date: Optional[datetime.date],
    rounds: Optional[int] = None,
    offset: int = 0,
    *,
    alternate_home_away_on_repeat: bool = False,
    teams: Optional[dict] = None,
    custom_date_generator=None,
) -> MatchCollection:
    """
    Build the (unsaved) matches of a draw for a stage or pool.

    ``rounds`` defaults to one full pass of the format; more rounds repeat
    the format. ``offset`` shifts the round numbers. Dates come from the
    season's mode (weekly or daily), skipping the season's and division's
    excluded dates, unless ``custom_date_generator`` is given. ``teams``
    replaces the mapping of numeric team references (0-based) for callers
    that place teams themselves.

    The same inputs against the same database always produce the same
    matches: team references are resolved against a totally ordered list
    of teams.
    """
    generator = draw_generator(target, draw_format, start_date)
    if teams:
        generator.teams.update(teams)
    return generator.generate(
        rounds,
        offset or 0,
        custom_date_generator=custom_date_generator,
        alternate_home_away_on_repeat=alternate_home_away_on_repeat,
    )
