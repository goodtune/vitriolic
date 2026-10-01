"""
The scheduling rules every administration tool applies when it sets the date,
time or place of a match: ``create_match``, ``reschedule_match``,
``schedule_matches``, ``auto_schedule`` and ``build_draw`` all go through
``ScheduleValidator`` so one rule is never enforced by one tool and missed by
another.

The rules, in the order they are checked:

1. **Dates** (``Match.clean``): not before the season starts, not on a date
   excluded for the season or for the division.
2. **Time slots**: when the season has time slot rules (``SeasonMatchTime``)
   the time must be one of the slots those rules produce on the match's date
   (``Season.get_timeslots``). A season without rules accepts any time.
3. **Clashes** (skipped with ``ignore_clashes``): no other match at the same
   place and time that day, and no team a side declares a clash with
   playing at the same time. Matches being moved in the same batch are
   judged by where they are going, not where they are now.

Team time preferences (``timeslots_after`` / ``timeslots_before``) are
checked by the admin scheduler's ``MatchScheduleForm``, which the tools bind
before asking this validator; like the admin scheduler, ``ignore_clashes``
waives them. ``ignore_clashes`` never waives a date or time slot rule.
"""

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db.models import Q

from tournamentcontrol.competition.models import Match


def validation_message(errors):
    """
    Flatten form or model validation errors into one readable sentence.
    """
    if isinstance(errors, ValidationError):
        errors = (
            errors.message_dict
            if hasattr(errors, "error_dict")
            else {NON_FIELD_ERRORS: errors.messages}
        )
    parts = []
    for field, messages in errors.items():
        name = "error" if field == NON_FIELD_ERRORS else field
        parts.append("%s: %s" % (name, " ".join(str(m) for m in messages)))
    return "; ".join(parts)


def _hhmm(time):
    return time.strftime("%H:%M")


class ScheduleValidator:
    """
    Check matches against the scheduling rules, remembering the places and
    times already handed out so that several matches scheduled together (a
    batch, or a draw being built) are checked against each other as well as
    against the database.

    ``moving`` holds the identifiers of matches whose current place in the
    database is about to be replaced; they are ignored when looking for
    clashes in the database (their new places are claimed instead).
    """

    def __init__(self, *, ignore_clashes=False, moving=()):
        self.ignore_clashes = ignore_clashes
        self.moving = {pk for pk in moving if pk is not None}
        # (date, place id, time) -> description of the claimant
        self._places = {}
        # (date, time) -> {team id: description of the claimant}
        self._teams = {}
        self._rules = {}
        self._slots = {}

    # -- time slots -----------------------------------------------------------

    def has_timeslot_rules(self, season):
        if season.pk not in self._rules:
            self._rules[season.pk] = season.timeslots.exists()
        return self._rules[season.pk]

    def timeslots(self, season, date):
        """The kick-off times the season's rules produce on ``date``."""
        key = (season.pk, date)
        if key not in self._slots:
            self._slots[key] = sorted(set(season.get_timeslots(date)))
        return self._slots[key]

    # -- rules ------------------------------------------------------------------

    def date_errors(self, match):
        """
        The model's date rules (season start, season and division exclusion
        dates). ``Match.clean`` also computes the kick-off instant.
        """
        try:
            match.clean()
        except ValidationError as exc:
            return ["Validation failed: " + validation_message(exc)]
        return []

    def time_errors(self, match):
        """The season's time slot rule, when it has one."""
        if match.time is None:
            return []
        season = match.stage.division.season
        if not self.has_timeslot_rules(season):
            return []
        slots = self.timeslots(season, match.date)
        if match.time in slots:
            return []
        when = f" on {match.date.isoformat()}" if match.date else ""
        if slots:
            valid = "valid: " + ", ".join(_hhmm(slot) for slot in slots)
        else:
            valid = "the season has no time slots on that date"
        return [
            "Validation failed: time: %s is not a time slot%s; %s."
            % (_hhmm(match.time), when, valid)
        ]

    def clash_errors(self, match):
        """
        Another match at the same place and time, or a team the sides clash
        with playing at the same time; in the database or already claimed by
        this validator.
        """
        if self.ignore_clashes or match.date is None:
            return []
        errors = []
        others = (
            Match.objects.filter(date=match.date)
            .exclude(pk__in=self.moving | ({match.pk} - {None}))
            .exclude(play_at=None, time=None)
        )
        play_at_id, time = match.play_at_id, match.time
        if play_at_id is not None and time is not None:
            claimant = self._places.get((match.date, play_at_id, time))
            if claimant is not None:
                errors.append(
                    "%s is already scheduled for this time & place."
                    % claimant.capitalize()
                )
            elif others.filter(play_at_id=play_at_id, time=time).exists():
                errors.append(
                    "Another match is already scheduled for this time & place."
                )
        if time is not None:
            claimed = self._teams.get((match.date, time), {})
            for team in (match.home_team, match.away_team):
                if team is None:
                    continue
                claimant = claimed.get(team.pk)
                if claimant is not None or (
                    others.filter(
                        Q(home_team=team) | Q(away_team=team), time=time
                    ).exists()
                ):
                    errors.append(
                        "%s are already playing at %s on %s%s."
                        % (
                            team.title,
                            _hhmm(time),
                            match.date.isoformat(),
                            f" ({claimant})" if claimant else "",
                        )
                    )
                for clash in team.team_clashes.all():
                    claimant = claimed.get(clash.pk)
                    if claimant is None and not (
                        others.filter(
                            Q(home_team=clash) | Q(away_team=clash), time=time
                        ).exists()
                    ):
                        continue
                    errors.append(
                        "%s must not play at the same time as %s (%s), who "
                        "are already scheduled at %s%s."
                        % (
                            team.title,
                            clash.title,
                            clash.division.title,
                            _hhmm(time),
                            f" ({claimant})" if claimant else "",
                        )
                    )
        return errors

    def errors(self, match, *, time=True, clashes=True, dates=True):
        """
        Every rule ``match`` (with its new date, time and place assigned)
        breaks; ``time`` and ``clashes`` can be left out when they are not
        being changed.
        """
        errors = []
        if dates:
            errors.extend(self.date_errors(match))
        if time:
            errors.extend(self.time_errors(match))
        if clashes:
            errors.extend(self.clash_errors(match))
        return errors

    def claim(self, match, description):
        """Record the place and time ``match`` now occupies."""
        if match.date is None or match.time is None:
            return
        if match.play_at_id is not None:
            self._places[(match.date, match.play_at_id, match.time)] = description
        teams = self._teams.setdefault((match.date, match.time), {})
        for team_id in (match.home_team_id, match.away_team_id):
            if team_id is not None:
                teams[team_id] = description
