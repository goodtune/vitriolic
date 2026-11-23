"""
The scoreboard of a ground: which match it shows, and that match's clock.

A scoreboard is a screen at a ground (or laid over its live stream) that
shows the score of the match being played and counts its periods down. The
score is the match's progress score, kept by a scorer; it is not the result.

The clock is not stored or pushed. It runs from one moment, the match's
scheduled time or the moment the scorer started it, through the periods and
breaks of the match's division. The server works out where the clock is when
it renders (``Clock.at``), and the page's script counts on from the same
numbers (``scoreboard.js``), so the two agree without a push every second.
"""

import dataclasses
import datetime
import hashlib
import json

from django.template import Context, Engine, TemplateDoesNotExist, TemplateSyntaxError
from django.templatetags.static import static
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext as _

from tournamentcontrol.competition.compops import queries
from tournamentcontrol.competition.compops.board_tag import RENDERED

#: The channel of a season's bus that its scoreboards listen to. A tap of a
#: scorer's button is news to a board, and noise in the ops desk's activity.
SCOPE = "scoreboard"

#: How long a finished match stays on the board before the next one takes it.
HOLD = datetime.timedelta(minutes=2)


@dataclasses.dataclass(frozen=True)
class Moment:
    """Where a clock is: the phase it is in and the seconds left of it."""

    #: ``ready`` (not started), ``before`` (to the start), ``period``,
    #: ``break`` or ``over``.
    kind: str
    #: The phase's place among the periods and breaks, from 0; ``None``
    #: before the first and after the last.
    index: int | None
    #: The period being played, or about to be, from 1.
    period: int | None
    #: Whole seconds left of the phase, rounded up as a countdown reads.
    remaining: int
    #: The seconds left exactly, for the tenths of a period's last minute.
    exact: float | None = dataclasses.field(default=None, compare=False)
    #: What the phase is called: "1st Half", "Half time", "Full time". Empty
    #: for the one period of a match that has only one.
    label: str = dataclasses.field(default="", compare=False)

    @property
    def display(self):
        # The last minute of a period is shown to a tenth of a second, cut
        # short, not rounded: the clock reads 0.0 only when the period is over.
        exact = self.remaining if self.exact is None else self.exact
        if self.kind == "period" and exact < 60:
            return f"{int(exact * 10) / 10:.1f}"
        minutes, seconds = divmod(self.remaining, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"


def ordinal(number):
    """``number`` as a place: 1st, 2nd, 3rd, 4th, 11th, 21st."""
    if number % 100 in (11, 12, 13):
        return f"{number}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


#: What a period is called when nothing says, from how many a match has:
#: two are halves, four are quarters, and any other number are periods.
PERIOD_NAMES = {2: "Half", 4: "Quarter"}

#: What the break after so many periods is called, in a match of so many.
#: The break in the middle of any even number of periods is half time.
BREAK_NAMES = {
    (4, 1): "Quarter time",
    (4, 3): "Three-quarter time",
}
HALF_TIME = "Half time"

#: What the clock says when it is not in a period or a break.
LABELS = {"ready": "Ready", "before": "Starts in", "over": "Full time"}


@dataclasses.dataclass(frozen=True)
class Clock:
    """The timing of one match: when it starts, and its periods and breaks."""

    #: When the clock runs from; ``None`` while it waits to be started.
    start: datetime.datetime | None
    periods: int
    #: Seconds in a period, and in the break between two.
    period: int
    pause: int
    #: What a period is called ("Chukka"), where it is not to be named from
    #: how many there are.
    name: str = ""
    #: Seconds in the break at half time, where it is not as long as the
    #: others: the break in the middle of an even number of periods.
    half: int | None = None

    def is_half_time(self, played):
        """Whether the break after ``played`` periods is the one at half time."""
        return self.periods % 2 == 0 and played * 2 == self.periods

    @property
    def phases(self):
        """The periods and the breaks between them, as (kind, seconds)."""
        phases = []
        for number in range(self.periods):
            pause = self.pause
            if self.half is not None and self.is_half_time(number):
                pause = self.half
            if number and pause:
                phases.append(("break", pause))
            phases.append(("period", self.period))
        return phases

    @property
    def phases_json(self):
        return json.dumps(self.phases)

    @property
    def names(self):
        """
        What each phase is called, in order: "1st Half", "Half time", "2nd
        Half". The periods are named from how many there are (halves,
        quarters, else periods) unless the match gives a name, and then its
        breaks are only breaks, but for a half time that has a length of its
        own. The one period of a match that has only one has no name: there
        is nothing to tell it from.
        """
        word = self.name or PERIOD_NAMES.get(self.periods, "Period")
        names = []
        played = 0
        for kind, _seconds in self.phases:
            if kind == "break":
                named = None
                if self.is_half_time(played) and (
                    not self.name or self.half is not None
                ):
                    named = HALF_TIME
                elif not self.name:
                    named = BREAK_NAMES.get((self.periods, played))
                names.append(named or "Break")
            else:
                played += 1
                names.append("" if self.periods == 1 else f"{ordinal(played)} {word}")
        return names

    @property
    def names_json(self):
        return json.dumps(self.names)

    @property
    def length(self):
        return datetime.timedelta(seconds=sum(seconds for _, seconds in self.phases))

    @property
    def end(self):
        return None if self.start is None else self.start + self.length

    @property
    def start_ms(self):
        return None if self.start is None else int(self.start.timestamp() * 1000)

    def at(self, now):
        if self.start is None:
            return Moment(
                "ready", None, 1, self.period, float(self.period), LABELS["ready"]
            )
        elapsed = (now - self.start).total_seconds()
        if elapsed < 0:
            # Rounded up, as a countdown reads: 0.4 seconds to go shows 00:01.
            return Moment(
                "before",
                None,
                1,
                int(-elapsed) + (elapsed % 1 > 0),
                -elapsed,
                LABELS["before"],
            )
        period = 0
        for index, (kind, seconds) in enumerate(self.phases):
            period += kind == "period"
            if elapsed < seconds:
                left = seconds - elapsed
                # The period a break leads to is the next one.
                return Moment(
                    kind,
                    index,
                    period + (kind == "break"),
                    int(left) + (left % 1 > 0),
                    left,
                    self.names[index],
                )
            elapsed -= seconds
        return Moment("over", None, None, 0, 0.0, LABELS["over"])


def timing(match):
    """
    The periods, the minutes in one, the minutes of a break, what a period is
    called and the minutes of half time (``None`` where it is as long as any
    other break) for ``match``: each its own if it has one, else its stage's,
    else its division's.
    Round matches of rugby sevens have halves of 7 minutes and the final has
    halves of 10, so the finals stage, or the final alone, says 10.
    """
    stage = match.stage
    owners = (match, stage, stage.division)

    def first(name):
        return next(
            (
                getattr(owner, name)
                for owner in owners
                if getattr(owner, name) is not None
            ),
            None,
        )

    # A name is text, and empty where a number would be missing.
    name = next(
        (owner.period_name for owner in owners if owner.period_name.strip()), ""
    )
    return (
        first("periods"),
        first("period_minutes"),
        first("break_minutes"),
        name,
        first("half_time_minutes"),
    )


def clock_for(match, ground):
    """
    The clock of ``match`` on ``ground``, or ``None`` when nothing gives it a
    period length (see ``timing``). It runs from when the scorer started it;
    else, at a venue whose clocks start on time, from the match's scheduled
    time.
    """
    periods, period_minutes, break_minutes, name, half_time_minutes = timing(match)
    if not period_minutes:
        return None
    start = match.clock_started_at
    if start is None and ground.venue.scoreboard_auto_start:
        start = match.datetime
    return Clock(
        start=start,
        periods=periods,
        period=period_minutes * 60,
        pause=break_minutes * 60,
        name=name.strip(),
        half=None if half_time_minutes is None else half_time_minutes * 60,
    )


def board_match(ground, now):
    """
    The match the ground's scoreboard shows at ``now``: the one being played;
    before the first, and once a match has been over for ``HOLD``, the next
    to come, with a countdown to its start. A match with no clock, or whose
    clock was never started, keeps the board until the next one's time.
    """
    day = ground.local_date(now)
    matches = list(queries.ground_runsheet(ground, day))
    started = [m for m in matches if m.datetime <= now]
    upcoming = [m for m in matches if m.datetime > now]
    current = started[-1] if started else None
    following = upcoming[0] if upcoming else None
    if current is None or following is None:
        return current or following
    clock = clock_for(current, ground)
    if clock is not None and clock.end is not None and now >= clock.end + HOLD:
        return following
    return current


def team_code(match, side):
    """
    A few letters for a team, for where its logo would go: its club's
    abbreviation, else the start of its name.
    """
    team = getattr(match, f"{side}_team")
    club = team.club if team is not None else None
    if club is not None and club.abbreviation:
        return club.abbreviation
    name = str(getattr(match, f"get_{side}_team_plain")())
    return "".join(character for character in name if character.isalnum())[:3].upper()


def score(match, side):
    """
    The score to show for one side: the progress score once one is kept,
    else the result if the match has one, else nothing scored.
    """
    progress = getattr(match, f"{side}_team_progress_score")
    if progress is not None:
        return progress
    return getattr(match, f"{side}_team_score") or 0


# --- templates written in the admin ---------------------------------------

#: The engine that renders a scoreboard template written in the admin. Such a
#: template is text that someone typed, so it is given very little: Django's
#: own tags and filters and ``{% board %}``, no other tag library, and no
#: loader, so it can neither include nor extend a template of the project.
ENGINE = Engine(
    dirs=[],
    app_dirs=False,
    loaders=[],
    libraries={},
    builtins=["tournamentcontrol.competition.compops.board_tag"],
    autoescape=True,
)

#: The scopes a template may be written at, nearest to the match first.
SCOPES = ("stage", "division", "season", "competition")


def template_for(season, match=None):
    """
    The scoreboard template written in the admin that applies, as
    ``(key, source)``: that of the match's stage, else its division, else the
    season, else the competition. ``(None, None)`` when none of them has one,
    and the project's own template draws the board.

    The key names the scope and carries a digest of the source, so a page
    can tell that another template has taken over, or that its own was
    edited, and load itself again.
    """
    owners = []
    if match is not None:
        owners += [("stage", match.stage), ("division", match.stage.division)]
    owners += [("season", season), ("competition", season.competition)]
    for scope, owner in owners:
        source = owner.scoreboard_template
        if source.strip():
            digest = hashlib.sha256(source.encode()).hexdigest()[:12]
            return f"{scope}:{owner.pk}:{digest}", source
    return None, None


def plain_context(context):
    """
    What a template written in the admin is given: names, numbers and times
    as plain values, and never a model instance. A template can follow an
    object to anything it holds (a season holds its YouTube secrets), and
    whoever may edit a stage would then read it off a scoreboard.
    """
    season, ground, match = context["season"], context["ground"], context["match"]
    clock, moment = context["clock"], context["moment"]
    plain = {
        "variant": context["variant"],
        "template_key": context["template_key"],
        "competition": {
            "title": season.competition.title,
            "slug": season.competition.slug,
        },
        "season": {"title": season.title, "slug": season.slug},
        "venue": {"title": ground.venue.title},
        "ground": {"title": ground.title, "slug": ground.slug},
        "match": None,
        "home": context["home"],
        "away": context["away"],
        "clock": None,
        "moment": None,
        "dots": context["dots"],
        "board_url": context["board_url"],
        "events_url": context["events_url"],
    }
    if match is not None:
        kick_off = timezone.localtime(match.datetime, context["tzinfo"])
        plain["match"] = {
            "pk": match.pk,
            "time": kick_off.strftime("%H:%M"),
            "label": match.label or "",
            "round": match.round,
            "division": match.stage.division.title,
            "stage": match.stage.title,
        }
    if clock is not None:
        plain["clock"] = {
            "periods": clock.periods,
            "period_minutes": clock.period // 60,
            "break_minutes": clock.pause // 60,
            "half_time_minutes": (clock.pause if clock.half is None else clock.half)
            // 60,
        }
        plain["moment"] = {
            "kind": moment.kind,
            "label": moment.label,
            "display": moment.display,
            "period": moment.period,
        }
        # What scoreboard.js counts the clock from; the element that carries
        # them also holds #sb-time and, if wanted, #sb-label.
        plain["clock_attrs"] = format_html(
            'id="sb-clock" data-match="{}" data-now="{}" data-start="{}" '
            'data-periods="{}" data-period="{}" data-pause="{}" data-names="{}" '
            'data-phases="{}"',
            match.pk,
            context["now_ms"],
            "" if clock.start_ms is None else clock.start_ms,
            clock.periods,
            clock.period,
            clock.pause,
            clock.names_json,
            clock.phases_json,
        )
    else:
        plain["clock_attrs"] = ""
    # What every scoreboard page needs, whatever it looks like.
    plain["attrs"] = format_html(
        'data-signals__ifmissing="{{board: \'{}\'}}" data-indicator="connected" '
        "data-effect=\"@get('{}', {{retryMaxCount: 1000}})\"",
        context["variant"],
        context["events_url"],
    )
    plain["scripts"] = format_html(
        '<script type="module" src="{}"></script><script src="{}"></script>',
        static("tournamentcontrol/competition/compops/datastar-1.0.4.js"),
        static("tournamentcontrol/competition/compops/scoreboard.js"),
    )
    plain["styles"] = format_html(
        '<link rel="stylesheet" href="{}">',
        static("tournamentcontrol/competition/compops/scoreboard.css"),
    )
    return plain


def render_custom(source, context, board_only=False):
    """
    Render a template written in the admin with ``context`` (see
    ``plain_context``): the whole page, or only what its ``{% board %}`` tag
    drew, which is what a live update sends.
    """
    boards = []
    page = ENGINE.from_string(source).render(Context({**context, RENDERED: boards}))
    if board_only:
        return boards[0] if boards else ""
    return page


#: A context for trying a template out before it is saved.
SAMPLE = {
    "variant": "display",
    "template_key": "sample",
    "competition": {"title": "Competition", "slug": "competition"},
    "season": {"title": "Season", "slug": "season"},
    "venue": {"title": "Venue"},
    "ground": {"title": "Ground", "slug": "ground"},
    "match": {
        "pk": 1,
        "time": "19:00",
        "label": "",
        "round": 1,
        "division": "Division",
        "stage": "Stage",
    },
    "home": {"name": "Home", "code": "HOM", "score": 0},
    "away": {"name": "Away", "code": "AWA", "score": 0},
    "clock": {"periods": 2, "period_minutes": 20, "break_minutes": 5},
    "moment": {"kind": "period", "label": "1st Half", "display": "20:00", "period": 1},
    "dots": [{"kind": "period", "state": "on"}],
    "clock_attrs": "",
    "attrs": "",
    "scripts": "",
    "styles": "",
    "board_url": "",
    "events_url": "",
}


def check_template(source):
    """
    Why ``source`` cannot be a scoreboard template, or ``None`` when it can:
    it must compile and render with what a board is given, and it must mark
    the part the live updates replace with ``{% board %}``.
    """
    if not source.strip():
        return None
    boards = []
    try:
        ENGINE.from_string(source).render(Context({**SAMPLE, RENDERED: boards}))
    except TemplateDoesNotExist as exc:
        return _(
            "A scoreboard template cannot include or extend another "
            "template (%(name)s)."
        ) % {"name": exc}
    except TemplateSyntaxError as exc:
        return _("This is not a template: %(error)s") % {"error": exc}
    if not boards:
        return _(
            "Put {% board %} and {% endboard %} around the part that changes "
            "while a match is played: the live updates replace what is "
            "between them."
        )
    return None
