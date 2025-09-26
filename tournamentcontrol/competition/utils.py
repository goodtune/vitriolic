import base64
import collections
import io
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import zip_longest
from operator import and_, or_
from typing import Iterable, Optional, Union
from zoneinfo import ZoneInfo

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Case, CharField, F, Func, Q, Value, When
from django.db.models.functions import Cast, Concat
from django.http import HttpResponse
from django.template.loader import select_template
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from PIL import Image

from touchtechnology.common.prince import prince
from tournamentcontrol.competition.draw.schemas import (
    MatchDescriptor,
    RoundDescriptor,
)

logger = logging.getLogger(__name__)

home_team_needs_progressing = and_(
    Q(home_team__isnull=True),
    or_(Q(home_team_undecided__isnull=False), Q(home_team_eval__isnull=False)),
)

away_team_needs_progressing = and_(
    Q(away_team__isnull=True),
    or_(Q(away_team_undecided__isnull=False), Q(away_team_eval__isnull=False)),
)

team_needs_progressing = and_(
    or_(home_team_needs_progressing, away_team_needs_progressing),
    Q(stage__division__season__complete=False),
)

legitimate_bye_match = and_(
    Q(is_bye=True), or_(Q(home_team__isnull=False), Q(away_team__isnull=False))
)

match_unplayed = or_(Q(home_team_score__isnull=True), Q(away_team_score__isnull=True))

stage_group_position_re = re.compile(
    r"""
    (?:
        S(?P<stage>\d+)         # stage number (optional)
    )?
    (?:
        G(?P<group>\d+)         # group number (optional)
    )?
    P(?P<position>\d+)          # position number
    """,
    re.VERBOSE,
)


class StageGroupPosition(Func):
    function = "vitriolic_stage_group_position"


def team_title_case_clause(team):
    return Case(
        When(
            Q(**{f"{team}__isnull": False}),
            then=F(f"{team}__title"),
        ),
        When(
            Q(**{f"{team}_eval__isnull": False}),
            then=Case(
                When(
                    Q(**{f"{team}_eval": "W"}),
                    then=Concat(
                        Value("Winner "),
                        F(f"{team}_eval_related__label"),
                    ),
                ),
                When(
                    Q(**{f"{team}_eval": "L"}),
                    then=Concat(
                        Value("Loser "),
                        F(f"{team}_eval_related__label"),
                    ),
                ),
                default=StageGroupPosition(
                    Cast(f"{team}_eval", output_field=CharField())
                ),
            ),
        ),
        When(
            Q(**{f"{team}_undecided__isnull": False}),
            then=Case(
                When(
                    ~Q(**{f"{team}_undecided__label": ""}),
                    then=F(f"{team}_undecided__label"),
                ),
                When(
                    ~Q(**{f"{team}_undecided__formula": ""}),
                    then=StageGroupPosition(
                        Cast(f"{team}_undecided__formula", output_field=CharField())
                    ),
                ),
                default=Value(None, output_field=CharField()),
            ),
        ),
        When(
            is_bye=True,
            then=Value('<span class="bye" title="Bye">Bye</span>'),
        ),
        default=Value(None, output_field=CharField()),
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
        pks = [each.pk for each in self]
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


def ceiling(
    value: Union[Decimal, int, float],
    factor: Union[Decimal, int, float] = 1,
) -> Decimal:
    """
    For a numerical ``value``, round it up to the nearest multiple of ``factor``.

        >>> ceiling(Decimal("3.5"))
        Decimal('4')
        >>> ceiling(13, 5)
        Decimal('15')
        >>> ceiling(3.5)
        Decimal('4')
        >>> ceiling(3.5, Decimal("0.75"))
        Decimal('3.75')

    :param value: number to be rounded up
    :param factor: multiplier to round up to
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    if not isinstance(factor, Decimal):
        factor = Decimal(str(factor))
    return (value / factor).quantize(1, rounding="ROUND_UP") * factor


def floor(
    value: Union[Decimal, int, float],
    factor: Union[Decimal, int, float] = 1,
):
    """
    For a numeric ``value``, round it down to the nearest multiple of ``factor``.

        >>> floor(Decimal("3.5"), Decimal("1.5"))
        Decimal('3.0')
        >>> floor(3, 2)
        Decimal('2')
        >>> floor(3.5)
        Decimal('3')
        >>> floor(Decimal("3.5"), 1.5)
        Decimal('3.0')
        >>> floor(2.5, 0.6)
        Decimal('2.4')

    :param value: number to be rounded down
    :param factor: multiplier to round down to
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    if not isinstance(factor, Decimal):
        factor = Decimal(str(factor))
    return (value / factor).quantize(1, rounding="ROUND_DOWN") * factor


def revpow(n: int, base: int) -> int:
    """
    Reverse of ``pow`` built-in function.

        >>> revpow(1, 2)
        0
        >>> revpow(2, 2)
        1
        >>> revpow(4, 2)
        2
        >>> revpow(8, 2)
        3
        >>> revpow(16, 2)
        4
        >>> revpow(32, 2)
        5
        >>> revpow(3, 2)
        Traceback (most recent call last):
          ...
        ValueError: 3 is not a power of 2

    :param n: number that is a power of base
    :param base: the base
    """
    res: float = math.log(n, base)
    if not res.is_integer():
        raise ValueError(f"{n} is not a power of {base}")
    return int(res)


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
    if isinstance(tz, str):
        tz = ZoneInfo(tz)
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
    # ensure we have a list so we can perform appends and inserts
    if not isinstance(teams, list):
        teams = [t for t in teams]

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


def round_robin_format(
    teams: Union[int, Iterable], rounds: Optional[int] = None
) -> str:
    """
    Generate a formatted DrawGenerator string for a round-robin tournament.

    This creates a complete round-robin schedule where every team plays every
    other team. The output uses DrawGenerator syntax compatible with the
    tournament system.

    Args:
        teams: either an integer (number of teams) or an iterable of teams
        rounds: number of rounds to generate (optional, defaults to complete
                round-robin)

    Returns:
        formatted string showing the tournament schedule in DrawGenerator format

    Examples:
        4-team round robin:
        >>> round_robin_format(4)
        ('ROUND\n1: 1 vs 4\n2: 2 vs 3\nROUND\n3: 1 vs 3\n4: 4 vs 2\n'
         'ROUND\n5: 1 vs 2\n6: 3 vs 4')

        Custom team names:
        >>> round_robin_format(['Red', 'Blue', 'Green'])
        ('ROUND\n1: Red vs 0\n2: Blue vs Green\nROUND\n3: Red vs Green\n'
         '4: 0 vs Blue\nROUND\n5: Red vs Blue\n6: Green vs 0')

    Note:
        - Teams are referenced by their 1-based position (1, 2, 3...)
        - Uneven number of teams will have a "bye" (represented as 0)
        - Each ROUND section contains matches played together
          (ie. before the next round)
        - Total matches for n teams: n*(n-1)/2
        - For 4 teams: 6 matches across 3 rounds
        - For 6 teams: 15 matches across 5 rounds
    """
    # If teams is an integer, convert it to a range starting from 1
    if isinstance(teams, int):
        teams = range(1, teams + 1)

    i, s = 1, ""
    for round in round_robin(teams, rounds):
        s += "ROUND\n"
        for home, away in round:
            s += "%s: %s vs %s\n" % (i, home, away)
            i += 1
    return s.strip()


def final_series_rounds(pools: int) -> int:
    """
    For a given number of pools, determine the correct number of rounds to play in a
    final series to fairly determine a winner.

        >>> final_series_rounds(1)
        1
        >>> final_series_rounds(2)
        2
        >>> final_series_rounds(3)  # stupid number
        Traceback (most recent call last):
          ...
        ValueError: Number of pools (3) is not a power of 2.
        >>> final_series_rounds(4)
        3
        >>> final_series_rounds(8)
        4
    """
    try:
        rounds = revpow(pools, 2)
    except ValueError as exc:
        raise ValueError(f"Number of pools ({pools}) is not a power of 2.") from exc
    return rounds + 1


def final_series_round_label(number_of_matches: int) -> str:
    if number_of_matches == 2:
        return _("Semi Final")
    if number_of_matches == 4:
        return _("Quarter Final")
    if number_of_matches >= 8:
        return _("Round of %d") % (number_of_matches * 2)
    return _("Final")


def single_elimination_final_format(number_of_pools, bronze_playoff=None):
    """
    For any number of pools, construct a single elimination draw format to
    find the champion team.

    :param number_of_pools: number of starting groups
    :param bronze_playoff: unicode label for 3rd place playoff. If None no
                           match will be scheduled.
    :return: list
    """
    # Start building our final series with the initial round. Each match is
    # ordered so that the pool from which the highest seeds were originally
    # placed (pool 1) are farthest away from the second highest seed (pool 2).
    # In effect, this means P1, P2, ... PN.

    if number_of_pools == 1:
        initial = RoundDescriptor(2, final_series_round_label(2))
        initial.add(MatchDescriptor(1, "P1", "P4", f"{initial.round_label} 1"))
        initial.add(MatchDescriptor(2, "P2", "P3", f"{initial.round_label} 2"))

    else:
        initial = RoundDescriptor(
            number_of_pools, final_series_round_label(number_of_pools)
        )

        for pool in range(number_of_pools):
            match = MatchDescriptor(
                pool + 1,
                "G%dP1" % (pool + 1),
                "G%dP2" % (number_of_pools - pool),
                f"{initial.round_label} {pool + 1}",
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
        matches_this_round = len(series[-1].matches) // 2

        this_round = RoundDescriptor(
            matches_this_round, final_series_round_label(matches_this_round)
        )

        for i in range(matches_this_round):
            match = MatchDescriptor(
                series[-1].matches[-1].match_id + i + 1,
                "W%s" % (series[-1].matches[i].match_id),
                "W%s" % (series[-1].matches[-1 - i].match_id),
                f"{this_round.round_label} {i + 1}",
            )
            this_round.add(match)

        series.append(this_round)

    # If we want to schedule a 3rd place playoff, add an extra match to the
    # final round we've already created.
    if bronze_playoff is not None:
        match = MatchDescriptor(
            series[-1].matches[0].match_id + 1,
            "L%s" % (series[-2].matches[0].match_id),
            "L%s" % (series[-2].matches[1].match_id),
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
        logger.debug("No stage specified in formula %r", formula)
        s = stage.comes_after
    else:
        try:
            s = stage.division.stages.all()[int(s) - 1]
        except IndexError:
            logger.exception("Invalid stage %r for division %r", s, stage.division)
            raise
    logger.debug("stage=%r", s)

    if g is None:
        logger.debug("No group specified in formula %r", formula)
    else:
        pools = s.pools.all().order_by("order")
        if pools.count() >= int(g):
            try:
                g = pools[int(g) - 1]
            except IndexError:
                logger.exception("Invalid group %r for stage %r", g, stage)
                raise
        else:
            pool_count = pools.count()
            logger.exception(
                "Invalid group %r for stage %r (stage has %d pools)", g, s, pool_count
            )
            raise IndexError(
                f"Invalid group {g} for stage {s} (stage has {pool_count} pools)"
            )
    logger.debug("group=%r", g)

    p = int(p)
    logger.debug("position=%r", p)

    return s, g, p


#
# Scorecards
#


def generate_scorecards(
    matches=None,
    templates=None,
    format="html",
    extra_context=None,
    stage=None,
    **kwargs,
):
    if extra_context is None:
        extra_context = {}

    context = {
        "matches": matches,
    }
    context.update(extra_context)

    template = select_template(templates)
    output = template.render(context)

    if format == "pdf":
        output = prince(output, **kwargs)

    if stage is not None:
        for match in matches:
            match.to_be_printed.remove(stage)

    return output


def generate_fixture_grid(
    season,
    dates=None,
    templates=None,
    format="html",
    extra_context=None,
    *,
    http_response=True,
    **kwargs,
):
    logger.info(
        "season=%r dates=%r templates=%r format=%r extra_context=%r kwargs=%r",
        season,
        dates,
        templates,
        format,
        extra_context,
        kwargs,
    )
    if dates is None:
        dates = season.matches.dates("date", "day")

    if templates is None:
        templates = ["tournamentcontrol/competition/admin/grid.html"]

    if extra_context is None:
        extra_context = {}

    matrices = collections.OrderedDict()

    play_at = season.get_places()

    for date in dates:
        matches = season.matches.select_related(
            "stage_group",
            "stage",
            "stage__division",
            "home_team",
            "home_team__club",
            "away_team",
            "away_team__club",
            "play_at",
        ).filter(date=date)

        times = sorted(
            {m.time for m in matches if m.time is not None}.union(
                season.get_timeslots(date)
            )
        )

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
        "matrices": matrices,
        "venues": season.venues.all(),
        "columns": play_at,
    }
    context.update(extra_context)

    template = select_template(templates)
    html = template.render(context)

    if format == "pdf":
        pdf = prince(html, **kwargs)
        if http_response:
            return HttpResponse(pdf, content_type="application/pdf")
        return pdf

    if http_response:
        return HttpResponse(html)
    return html


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
    user = UserModel.objects.filter(person__in=people.values("person"))

    return (user, match.stage.division.season.forfeit_notifications.all())


#
# regrade
#


def regrade(team, to, from_date=None):
    Division = apps.get_model("competition", "Division")
    Team = apps.get_model("competition", "Team")

    assert isinstance(team, Team), "team is not a Team instance"
    assert isinstance(to, Division), "to is not a Division instance"
    assert team.division != to, "move to same Division is not allowed"
    assert team.division.season == to.season, "move to different Season is not allowed"

    # Work out the regrade date if not specified
    if from_date is None:
        from_date = team.matches.filter(match_unplayed).earliest("date").date

    # Update the sequence numbers of all teams in the current division to keep
    # them in order without any gaps
    team.division.teams.filter(order__gt=team.order).update(order=F("order") - 1)

    # All unplayed matches that this team is assigned to play need to be turned
    # into byes, removing them from the home_team and away_team fields. Strip
    # the time and field also.
    old_matches = team.matches.filter(match_unplayed, date__gte=from_date)
    old_matches.filter(home_team=team).update(
        home_team=None, is_bye=True, time=None, datetime=None, play_at=None
    )
    old_matches.filter(away_team=team).update(
        away_team=None, is_bye=True, time=None, datetime=None, play_at=None
    )

    # Move team into the bye matches in the new division.
    new_matches = to.matches.filter(legitimate_bye_match, date__gte=from_date)
    new_matches.filter(home_team=None).update(home_team=team, is_bye=False)
    new_matches.filter(away_team=None).update(away_team=team, is_bye=False)

    # Determine the highest sequence value in the target division and assign
    # that to our team. If it throws an DoesNotExist exception, the division
    # is empty and we need to set it to 1.
    try:
        team.order = to.teams.latest("order").order + 1
    except Team.DoesNotExist:
        team.order = 1


#
# label_from_instance utilities
#


def team_and_division(o):
    "For use on Model.team_clashes as label_from_instance argument."
    return "%s (%s)" % (o.title, o.division.title)


#
# Image processing utilities
#


@dataclass(frozen=True)
class ThumbnailPreview:
    """
    Result of thumbnail preview generation.

    Attributes:
        image_data: Raw image bytes for the preview image, or None if generation failed
        original_mime_type: MIME type of the original image, or None if unknown
    """

    image_data: bytes | None = None
    original_mime_type: str | None = None

    def to_data_url(self) -> str | None:
        """
        Convert the thumbnail preview to a base64 data URL for use in templates.

        Returns:
            Base64 data URL string, or None if no image data is available
        """
        if not self.image_data:
            return None

        preview_data = base64.b64encode(self.image_data).decode("utf-8")
        return f"data:image/jpeg;base64,{preview_data}"


def create_thumbnail_response(image_data, width=None, height=None):
    """
    Create an HttpResponse for serving thumbnail image data.

    Args:
        image_data (bytes): Raw image data
        width (int, optional): Maximum width for resizing
        height (int, optional): Maximum height for resizing

    Returns:
        HttpResponse: Image response with appropriate headers

    Raises:
        Http404: If no image data provided or processing fails
    """
    from django.http import Http404, HttpResponse

    if not image_data:
        raise Http404("No thumbnail available")

    # If dimensions specified, create a resized preview
    if width is not None and height is not None:
        # Validate dimensions
        if width > 2048 or height > 2048 or width < 1 or height < 1:
            raise Http404("Dimensions out of allowed range (1-2048)")

        preview_result = create_thumbnail_preview(
            image_data, max_width=width, max_height=height
        )
        if preview_result.image_data:
            response_data = preview_result.image_data
            content_type = "image/jpeg"  # Preview is always JPEG
        else:
            raise Http404("Failed to create thumbnail preview")
    else:
        # Serve original data as-is
        response_data = image_data
        # Try to detect content type from data, default to image/jpeg
        if image_data.startswith(b"\xff\xd8\xff"):
            content_type = "image/jpeg"
        elif image_data.startswith(b"\x89PNG\r\n\x1a\n"):
            content_type = "image/png"
        elif image_data.startswith(b"GIF"):
            content_type = "image/gif"
        else:
            content_type = "image/jpeg"  # Default fallback

    response = HttpResponse(response_data, content_type=content_type)
    response["Cache-Control"] = "max-age=3600"  # Cache for 1 hour
    return response


def create_thumbnail_preview(
    image_data, max_width=640, max_height=480, quality=90
) -> ThumbnailPreview:
    """
    Create a downscaled preview image from binary image data.

    Args:
        image_data (bytes): Binary image data
        max_width (int): Maximum width for the preview
        max_height (int): Maximum height for the preview
        quality (int): JPEG compression quality (1-100)

    Returns:
        ThumbnailPreview: Contains raw image_data bytes and original_mime_type, or None values if processing fails
    """
    try:
        # Open the image from binary data
        image = Image.open(io.BytesIO(image_data))

        # Get original format info
        original_format = image.format
        original_mime = (
            f"image/{original_format.lower()}" if original_format else "image/jpeg"
        )

        # Convert to RGB if necessary (for JPEG output)
        if image.mode in ("RGBA", "LA", "P"):
            # Create a white background for transparency
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(
                image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None
            )
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Calculate the thumbnail size maintaining aspect ratio
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

        # Save to a BytesIO buffer as JPEG for efficient preview
        output_buffer = io.BytesIO()
        image.save(output_buffer, format="JPEG", quality=quality, optimize=True)

    except Exception as e:
        logger.warning(f"Failed to create thumbnail preview: {e}")
        return ThumbnailPreview()

    return ThumbnailPreview(output_buffer.getvalue(), original_mime)
