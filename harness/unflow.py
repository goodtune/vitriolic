"""Take out of the database what one run of the flow put there.

The flow ends every title and last name it invents with the run's stamp (six
digits, the time of day), so everything of one run can be found by that
suffix and nothing else is touched. ``python -m harness unflow <stamp>``
deletes it through the ORM, children before parents, because most foreign
keys of the competition models protect their target. ``shots.sh`` runs it
for each width's stamp after the flow, so that a capture always shows the
seed alone. It is safe to run twice: the second run finds nothing.
"""

import logging
import re
import sys
from collections import Counter

from django.db import transaction
from django.db.models import QuerySet
from enrolment.models import (
    ClassGroup,
    Grade,
    SchoolYear,
    Student,
    Teacher,
)

from touchtechnology.common.models import SitemapNode
from touchtechnology.content.models import (
    NodeContent,
    Page,
    PageContent,
    Redirect,
)
from touchtechnology.news.models import Article, Category
from tournamentcontrol.competition.models import (
    Club,
    ClubAssociation,
    ClubRole,
    Competition,
    Division,
    DivisionExclusionDate,
    DrawFormat,
    Ground,
    LadderEntry,
    LadderSummary,
    Match,
    MatchScoreSheet,
    Person,
    Season,
    SeasonAssociation,
    SeasonExclusionDate,
    SeasonMatchTime,
    SeasonReferee,
    SimpleScoreMatchStatistic,
    Stage,
    StageGroup,
    Team,
    TeamAssociation,
    TeamRole,
    UndecidedTeam,
    Venue,
)

logger = logging.getLogger(__name__)

#: A run's stamp: the time of day the flow started, as ``HHMMSS``.
STAMP = re.compile(r"\d{6}")


def school_year(stamp: str) -> str:
    """The title of the flow's school year, which ``flow.State.year`` derives."""
    return "9" + stamp[-3:]


def _remove(queryset: QuerySet, removed: Counter) -> None:
    """Delete ``queryset`` and add what went, by model, to ``removed``."""
    if not queryset.exists():
        return
    __, per_model = queryset.delete()
    removed.update(per_model)


def _enrolment(stamp: str, suffix: str, removed: Counter) -> None:
    # The flow's classes go with their enrolments, attendance, assessments,
    # scores and report cards. Its year goes once no class is left in it (it
    # is the flow's alone, but a class of anyone else's would keep it). The
    # grade was protected by the classes.
    _remove(ClassGroup.objects.filter(title__endswith=suffix), removed)
    _remove(
        SchoolYear.objects.filter(title=school_year(stamp), classes__isnull=True),
        removed,
    )
    _remove(Student.objects.filter(last_name__endswith=suffix), removed)
    _remove(Teacher.objects.filter(last_name__endswith=suffix), removed)
    _remove(Grade.objects.filter(title__endswith=suffix), removed)


def _news(suffix: str, removed: Counter) -> None:
    _remove(Article.objects.filter(headline__endswith=suffix), removed)
    _remove(Category.objects.filter(title__endswith=suffix), removed)


def _content(suffix: str, removed: Counter) -> None:
    _remove(Redirect.objects.filter(label__endswith=suffix), removed)
    nodes = SitemapNode.objects.filter(title__endswith=suffix)
    pages = [node.object for node in nodes if isinstance(node.object, Page)]
    _remove(NodeContent.objects.filter(node__in=nodes), removed)
    _remove(PageContent.objects.filter(page__in=pages), removed)
    _remove(nodes, removed)
    for page in pages:
        _remove(Page.objects.filter(pk=page.pk), removed)


def _competition(suffix: str, removed: Counter) -> None:
    competitions = Competition.objects.filter(title__endswith=suffix)
    seasons = Season.objects.filter(competition__in=competitions)
    divisions = Division.objects.filter(season__in=seasons)
    stages = Stage.objects.filter(division__in=divisions)
    teams = Team.objects.filter(division__in=divisions)
    matches = Match.objects.filter(stage__in=stages)

    # The results first, then the matches that hold them, which protect the
    # teams, the places the teams are waiting for and the grounds.
    _remove(SimpleScoreMatchStatistic.objects.filter(match__in=matches), removed)
    _remove(MatchScoreSheet.objects.filter(match__in=matches), removed)
    _remove(LadderEntry.objects.filter(match__in=matches), removed)
    _remove(LadderEntry.objects.filter(opponent__in=teams), removed)
    _remove(LadderSummary.objects.filter(team__in=teams), removed)
    _remove(matches, removed)
    _remove(UndecidedTeam.objects.filter(stage__in=stages), removed)
    _remove(TeamAssociation.objects.filter(team__in=teams), removed)
    _remove(teams, removed)
    _remove(StageGroup.objects.filter(stage__in=stages), removed)
    _remove(stages, removed)
    _remove(DivisionExclusionDate.objects.filter(division__in=divisions), removed)
    _remove(divisions, removed)

    # What belongs to the season itself: its venues, with their grounds, its
    # times, dates and officials.
    _remove(SeasonReferee.objects.filter(season__in=seasons), removed)
    _remove(SeasonAssociation.objects.filter(season__in=seasons), removed)
    _remove(SeasonExclusionDate.objects.filter(season__in=seasons), removed)
    _remove(SeasonMatchTime.objects.filter(season__in=seasons), removed)
    venues = Venue.objects.filter(season__in=seasons)
    _remove(Ground.objects.filter(venue__in=venues), removed)
    _remove(venues, removed)
    _remove(seasons, removed)

    # The roles of the competition, and then the competition (its list of
    # clubs is only a link, which goes with it).
    _remove(ClubRole.objects.filter(competition__in=competitions), removed)
    _remove(TeamRole.objects.filter(competition__in=competitions), removed)
    _remove(competitions, removed)


def _clubs_and_people(suffix: str, removed: Counter) -> None:
    people = Person.objects.filter(last_name__endswith=suffix)
    clubs = Club.objects.filter(title__endswith=suffix)
    _remove(TeamAssociation.objects.filter(person__in=people), removed)
    _remove(ClubAssociation.objects.filter(person__in=people), removed)
    _remove(ClubAssociation.objects.filter(club__in=clubs), removed)
    _remove(SeasonReferee.objects.filter(person__in=people), removed)
    _remove(SeasonAssociation.objects.filter(person__in=people), removed)
    _remove(people, removed)
    _remove(clubs, removed)


def unflow(stamp: str) -> Counter:
    """
    Delete everything the flow made under ``stamp``, in one transaction, and
    return how many rows of each model went. A stamp that is not six digits
    is refused, since an empty suffix would match everything.
    """
    if not STAMP.fullmatch(stamp):
        raise ValueError(f"a flow stamp is six digits (HHMMSS), not {stamp!r}")
    suffix = " " + stamp
    removed: Counter = Counter()
    with transaction.atomic():
        _enrolment(stamp, suffix, removed)
        _news(suffix, removed)
        _content(suffix, removed)
        _competition(suffix, removed)
        _clubs_and_people(suffix, removed)
        _remove(DrawFormat.objects.filter(name__endswith=suffix), removed)
    return removed


def main(argv: list[str]) -> int:
    """``python -m harness unflow <stamp>...``: print what each stamp removed."""
    if not argv:
        print("usage: python -m harness unflow <stamp>...", file=sys.stderr)
        return 64
    for stamp in argv:
        try:
            removed = unflow(stamp)
        except ValueError as exc:
            print(f"unflow: {exc}", file=sys.stderr)
            return 64
        # The rows a delete took with it (the links of many-to-many fields)
        # are counted too; only the models are worth a line each.
        counts = ", ".join(
            f"{label.rsplit('.', 1)[-1]} {count}"
            for label, count in sorted(removed.items())
            if count
        )
        detail = f": {counts}" if counts else ""
        print(f"unflow {stamp}: removed {sum(removed.values())} rows{detail}")
    return 0
