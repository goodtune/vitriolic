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

from tournamentcontrol.competition.models import Match, Team


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
        # date -> what the database already has booked on it
        self._db = {}
        # team id -> the teams it declares a clash with
        self._clash_cache = {}

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

    def _booked(self, date):
        """
        The places and teams already taken on ``date`` in the database, read
        once per date (matches being moved excluded): ``(places, teams)``
        where ``places`` maps ``(place id, time)`` and ``teams`` maps
        ``(team id, time)`` to the identifiers of the matches holding them.
        """
        if date not in self._db:
            places, teams = {}, {}
            for pk, time, play_at_id, home_id, away_id in (
                Match.objects.filter(date=date)
                .exclude(pk__in=self.moving)
                .exclude(play_at=None, time=None)
                .values_list("pk", "time", "play_at_id", "home_team_id", "away_team_id")
            ):
                if time is None:
                    continue
                if play_at_id is not None:
                    places.setdefault((play_at_id, time), set()).add(pk)
                for team_id in (home_id, away_id):
                    if team_id is not None:
                        teams.setdefault((team_id, time), set()).add(pk)
            self._db[date] = (places, teams)
        return self._db[date]

    def prefetch_clashes(self, team_ids):
        """
        Load the declared clashes of every team in ``team_ids`` in one query,
        for a batch about to be checked.
        """
        team_ids = {pk for pk in team_ids if pk is not None} - set(self._clash_cache)
        if not team_ids:
            return
        for team_id in team_ids:
            self._clash_cache[team_id] = []
        through = Team.team_clashes.through
        for link in through.objects.filter(from_team_id__in=team_ids).select_related(
            "to_team__division"
        ):
            self._clash_cache[link.from_team_id].append(link.to_team)

    def _clashes(self, team):
        """The teams ``team`` declares a clash with, read once per team."""
        if team.pk not in self._clash_cache:
            self._clash_cache[team.pk] = list(
                team.team_clashes.select_related("division")
            )
        return self._clash_cache[team.pk]

    def clash_errors(self, match):
        """
        Another match at the same place and time, the same team playing
        twice at once, or a team the sides clash with playing at the same
        time; in the database or already claimed by this validator. The
        database is read once per date and each team's clashes once, so a
        batch costs a handful of queries rather than several per match.
        """
        if self.ignore_clashes or match.date is None:
            return []
        errors = []
        booked_places, booked_teams = self._booked(match.date)
        others = {match.pk} - {None}

        def taken(booked, key):
            return bool(booked.get(key, set()) - others)

        play_at_id, time = match.play_at_id, match.time
        if play_at_id is not None and time is not None:
            claimant = self._places.get((match.date, play_at_id, time))
            if claimant is not None:
                errors.append(
                    "%s is already scheduled for this time & place."
                    % claimant.capitalize()
                )
            elif taken(booked_places, (play_at_id, time)):
                errors.append(
                    "Another match is already scheduled for this time & place."
                )
        if time is not None:
            claimed = self._teams.get((match.date, time), {})
            for team in (match.home_team, match.away_team):
                if team is None:
                    continue
                claimant = claimed.get(team.pk)
                if claimant is not None or taken(booked_teams, (team.pk, time)):
                    errors.append(
                        "%s are already playing at %s on %s%s."
                        % (
                            team.title,
                            _hhmm(time),
                            match.date.isoformat(),
                            f" ({claimant})" if claimant else "",
                        )
                    )
                for clash in self._clashes(team):
                    claimant = claimed.get(clash.pk)
                    if claimant is None and not taken(booked_teams, (clash.pk, time)):
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
