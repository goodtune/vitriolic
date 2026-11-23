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

from tournamentcontrol.competition.compops import queries

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

    @property
    def label(self):
        return {
            "ready": "Ready",
            "before": "Starts in",
            "period": f"Period {self.period}",
            "break": "Break",
            "over": "Full time",
        }[self.kind]

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


@dataclasses.dataclass(frozen=True)
class Clock:
    """The timing of one match: when it starts, and its periods and breaks."""

    #: When the clock runs from; ``None`` while it waits to be started.
    start: datetime.datetime | None
    periods: int
    #: Seconds in a period, and in the break between two.
    period: int
    pause: int

    @property
    def phases(self):
        """The periods and the breaks between them, as (kind, seconds)."""
        phases = []
        for number in range(self.periods):
            if number and self.pause:
                phases.append(("break", self.pause))
            phases.append(("period", self.period))
        return phases

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
            return Moment("ready", None, 1, self.period, float(self.period))
        elapsed = (now - self.start).total_seconds()
        if elapsed < 0:
            # Rounded up, as a countdown reads: 0.4 seconds to go shows 00:01.
            return Moment(
                "before", None, 1, int(-elapsed) + (elapsed % 1 > 0), -elapsed
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
                )
            elapsed -= seconds
        return Moment("over", None, None, 0)


def timing(match):
    """
    The periods, the minutes in one and the minutes of a break for ``match``:
    each its own number if it has one, else its stage's, else its division's.
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

    return first("periods"), first("period_minutes"), first("break_minutes")


def clock_for(match, ground):
    """
    The clock of ``match`` on ``ground``, or ``None`` when nothing gives it a
    period length (see ``timing``). It runs from when the scorer started it;
    else, at a venue whose clocks start on time, from the match's scheduled
    time.
    """
    periods, period_minutes, break_minutes = timing(match)
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
