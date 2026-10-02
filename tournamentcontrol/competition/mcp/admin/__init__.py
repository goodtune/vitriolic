"""
Model Context Protocol (MCP) tools for *administering* the competition
management system.

Where ``tournamentcontrol.competition.mcp`` answers the questions people ask
about a competition, this toolset does the work a competition administrator
does in the admin site: building a competition up from scratch
(competitions, seasons, venues and grounds, divisions, teams, stages and
pools, matches), scheduling, result entry, referee appointments and live
streaming.

Reuse of business rules
-----------------------
Every change goes through the same ``ModelForm`` the admin site uses for
that record (``CompetitionForm``, ``SeasonForm``, ``MatchEditForm``,
``MatchResultForm`` and so on), so the validation and side effects those
forms carry apply here too; the YouTube side effects the admin views add
around the forms are mirrored for the live stream tools. A form is bound to
the record's current values with the requested changes laid over them, so
a tool only needs the arguments that change.

Authentication and authorization
--------------------------------
The toolset is served by ``views.AdminMCPView`` which only admits staff
users (``user.is_staff``), the same gate as the admin site. Each tool then
checks the model permission the equivalent admin view checks
(``competition.add_<model>`` to create, ``competition.change_<model>`` to
change and ``competition.delete_<model>`` to delete), accepted either
globally or on the specific object through django-guardian, exactly as
``touchtechnology.common.sites.generic_edit`` and ``generic_delete`` do.
Read-only administration tools need a staff user; those that reveal stream
keys need ``competition.change_season`` for the season.

Errors
------
A tool that cannot do what was asked raises ``ToolError`` (permission
denied, record not found, validation failure, a rule such as "a match
being live streamed cannot be moved"), which the client receives as an
error result carrying the message.
"""

import datetime
import html
import logging
from typing import Any, Literal

from dateutil.rrule import DAILY, WEEKLY
from django.conf import settings
from django.contrib.postgres.forms import SplitArrayWidget
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, ProtectedError, Q
from django.forms.widgets import MultiWidget
from django.utils import timezone
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from tournamentcontrol.competition.admin import (
    YOUTUBE_AUTH_EXPIRED_MESSAGE,
    next_related_factory,
)
from tournamentcontrol.competition.dashboard import (
    matches_require_basic_results,
)
from tournamentcontrol.competition.draw.generators import DrawGenerator
from tournamentcontrol.competition.draw.schemas import WIN_LOSE_RE
from tournamentcontrol.competition.draw.services import (
    draw_generator,
    draw_target_team_count,
    generate_stage_draw,
    suitable_draw_formats,
)
from tournamentcontrol.competition.forms import (
    CompetitionForm,
    DivisionForm,
    DrawFormatForm,
    GroundForm,
    LiveStreamKeyForm,
    MatchRefereeForm,
    MatchResultForm,
    MatchScheduleForm,
    MatchStreamForm,
    SeasonForm,
    StageForm,
    StageGroupForm,
    TeamForm,
    VenueForm,
)
from tournamentcontrol.competition.mcp import (
    MAX_LIMIT,
    CompetitionToolset,
    _clamp,
    _match_status,
    _match_summary,
    _place,
    _ref,
    _team_ref,
    _tzname,
    build_server,
    tool_annotations,
)
from tournamentcontrol.competition.mcp.admin.forms import (
    AgentMatchEditForm,
    AgentMatchStreamForm,
    SeasonMatchTimeForm,
    position_eval_error,
)
from tournamentcontrol.competition.mcp.admin.scheduling import (
    ScheduleValidator,
)
from tournamentcontrol.competition.mcp.admin.scheduling import (
    validation_message as _validation_message,
)
from tournamentcontrol.competition.models import (
    Competition,
    Division,
    DivisionExclusionDate,
    DrawFormat,
    Ground,
    LiveStreamKey,
    Match,
    Place,
    Season,
    SeasonExclusionDate,
    SeasonMatchTime,
    Stage,
    StageGroup,
    Team,
    Venue,
)
from tournamentcontrol.competition.tasks import sync_live_stream

logger = logging.getLogger(__name__)

#: The most builds ``build_draw`` and items ``schedule_matches`` take at once.
MAX_BUILDS = 50
MAX_SCHEDULE_ITEMS = 500

#: Text inputs that agents (or the clients relaying them) sometimes send
#: HTML-escaped; they are stored as plain text and escaped when rendered.
PLAIN_TEXT_FIELDS = {"title", "short_title", "label", "name"}

SeasonMode = Literal["season", "tournament"]
SEASON_MODES = {"season": WEEKLY, "tournament": DAILY}
LiveStreamPrivacyName = Literal["public", "private", "unlisted"]

ADMIN_INSTRUCTIONS = """
Competition administration tools
================================

These tools act on behalf of the signed-in administrator and apply the same
permissions as the admin site. Build a competition top down: `create_competition`,
`create_season`, then `create_venue` and `create_ground` for where matches
are played, `create_division`, `create_team` (per division), `create_stage`
and `create_pool` (teams are placed in pools with `update_pool`). Use the read
tools (`search`, `get_season`, `list_teams`, `list_matches`, `get_match`,
`get_ladder`) to find identifiers and to confirm each step; as an
administrator you also see disabled competitions and draft divisions.

Draws: do not create a season's matches one by one. Configure the season the
way the admin site's Draw Generation wizard expects and let the server build
the draw:

1. `create_timeslot` for the kick-off times (check with `get_timeslots`) and
   `add_season_exclusion_dates` / `add_division_exclusion_dates` for breaks;
2. find or create a draw format (`list_draw_formats`, `preview_draw_format`,
   `create_draw_format`): round robins for the regular season, and finals
   formats using ladder positions (P1), pool positions (G1P2) and winners or
   losers of earlier matches (W1, L1);
3. `build_draw` for every stage or pool in one call, first with `dry_run` to
   check the plan; dates follow the season's mode and skip excluded dates;
4. `schedule_matches` (or `auto_schedule`, a date at a time) to give the
   matches their times and grounds in one call.

`create_match` remains for one-off matches and repairs; it accepts the same
evals (`home_team_eval`, `home_team_eval_related_id`, ...) as a draw format.

Scheduling: `reschedule_match` sets the date, time and place (venue or
ground) of one match and `schedule_matches` of many at once. Every path that
sets a date or time applies the same rules: not before the season starts or
on a date excluded for the season or division; a time from the season's
time slots when it has any; the teams' time preferences; and, unless
`ignore_clashes`, no clash of place and time, of a team with itself or with
a team it declares a clash with. `ignore_clashes` waives the clash checks
and time preferences only, never excluded dates or time slots.
`swap_match_allocations` exchanges the date, time and place of two matches.
None of them will move a match that is being live streamed; remove the live
stream first.

Results: `list_matches_awaiting_results` finds matches that have been played
without a result; `record_match_result` enters or revises scores, forfeits
and bye processing, which updates the ladders.

Live streaming (seasons with live streaming enabled and YouTube credentials
configured): `list_streamed_grounds` and `enable_ground_live_stream` /
`disable_ground_live_stream` manage the camera positions and their stream
keys; `enable_match_live_stream` / `disable_match_live_stream` schedule or
withdraw the broadcast of a match; `list_season_stream_keys`,
`create_season_stream_key` and `delete_season_stream_key` manage the pool of
keys used by ad-hoc events (`list_season_stream_events`).

Every tool that changes data reports the record as saved. Match tools take
`verbose`: false returns only the identifiers and the scheduling fields, which
keeps long sessions small. A tool that cannot proceed (missing permission, a
rule such as "the stream key is in use", or a validation failure) returns an
error explaining why.
""".strip()


class BuildSpec(BaseModel):
    """One stage or pool to build a draw for (see ``build_draw``)."""

    stage_id: int | None = Field(
        None, description="The stage to build (a stage without pools)."
    )
    pool_id: int | None = Field(None, description="The pool to build.")
    draw_format_id: int | None = Field(
        None, description="A saved draw format (see list_draw_formats)."
    )
    draw_format_text: str | None = Field(
        None, description="Draw format text, instead of a saved format."
    )
    start_date: datetime.date | None = Field(
        None,
        description="The date of the first round; defaults to the season's "
        "start date.",
    )
    rounds: int | None = Field(
        None,
        ge=1,
        description="How many rounds to build; defaults to one pass of the "
        "format, more repeat it.",
    )
    offset: int = Field(0, description="Added to every round number.")
    alternate_home_away_on_repeat: bool = Field(
        False,
        description="Swap home and away on every second pass through the format.",
    )


class ScheduleItem(BaseModel):
    """The new date, time and/or place of one match (see ``schedule_matches``)."""

    match_id: int
    date: datetime.date | None = None
    time: datetime.time | None = None
    place_id: int | None = Field(
        None, description="A venue of the season or one of its grounds."
    )


def _coerce(model, value, what):
    if isinstance(value, model):
        return value
    try:
        return model.model_validate(value)
    except PydanticValidationError as exc:
        raise ToolError(
            "%s: %s"
            % (
                what,
                "; ".join(
                    "%s: %s" % (".".join(str(p) for p in e["loc"]) or "value", e["msg"])
                    for e in exc.errors()
                ),
            )
        )


def _hhmm(time):
    return time.strftime("%H:%M") if time else None


def _iso(date):
    return date.isoformat() if date else None


def _compact_match(match, now, today):
    """
    The identifiers and scheduling fields of a match, for tools called
    with ``verbose=False``.
    """
    return {
        "id": match.pk,
        "round": match.round,
        "date": _iso(match.date),
        "time": _hhmm(match.time),
        "place_id": match.play_at_id,
        "home_team_id": match.home_team_id,
        "away_team_id": match.away_team_id,
        "status": _match_status(match, now, today),
    }


def _draw_format_summary(draw_format, text=True):
    res = {
        "id": draw_format.pk,
        "name": draw_format.name,
        "teams": draw_format.teams,
        "is_final": draw_format.is_final,
    }
    if text:
        res["text"] = draw_format.text
    return res


def _format_structure(generator, teams=None):
    """
    The rounds and matches of a parsed draw format, with the warnings an
    agent should know about before using it.
    """
    rounds = []
    warnings = []
    seen = {}
    highest = 0
    for round in generator.rounds:
        matches = []
        in_round = {}
        for descriptor in round.matches:
            for ref in (descriptor.home_team, descriptor.away_team):
                if ref.isdigit():
                    highest = max(highest, int(ref))
                    if ref in in_round:
                        warnings.append(
                            "Team %s plays more than once in round %d."
                            % (ref, round.count)
                        )
                    in_round[ref] = True
                win_lose = WIN_LOSE_RE.fullmatch(ref)
                if win_lose and win_lose.group("match_id") not in seen:
                    warnings.append(
                        "Match %s refers to %s, but match %s is not in an "
                        "earlier round."
                        % (descriptor.match_id, ref, win_lose.group("match_id"))
                    )
            matches.append(
                {
                    "id": descriptor.match_id,
                    "home": descriptor.home_team,
                    "away": descriptor.away_team,
                    "label": descriptor.match_label or round.round_label or None,
                }
            )
        for descriptor in round.matches:
            seen[descriptor.match_id] = round.count
        rounds.append(
            {
                "round": round.count,
                "label": round.round_label or None,
                "matches": matches,
            }
        )
    res = {
        "rounds": rounds,
        "round_count": len(rounds),
        "match_count": sum(len(r["matches"]) for r in rounds),
        "highest_team_number": highest,
    }
    if teams is not None:
        if highest > teams:
            warnings.append(
                "Teams %s are byes for %d teams."
                % (", ".join(str(n) for n in range(teams + 1, highest + 1)), teams)
            )
        pairings = set()
        for round in rounds:
            for m in round["matches"]:
                if m["home"].isdigit() and m["away"].isdigit():
                    a, b = int(m["home"]), int(m["away"])
                    if a <= teams and b <= teams:
                        pairings.add(frozenset((a, b)))
        expected = teams * (teams - 1) // 2
        res["pairings"] = {"covered": len(pairings), "possible": expected}
    res["warnings"] = warnings
    return res


def _exclusion_summary(exclusion):
    return {"id": exclusion.pk, "date": exclusion.date.isoformat()}


def _timeslot_summary(timeslot):
    return {
        "id": timeslot.pk,
        "start": _hhmm(timeslot.start),
        "interval": timeslot.interval,
        "count": timeslot.count,
        "start_date": _iso(timeslot.start_date),
        "end_date": _iso(timeslot.end_date),
    }


def _perm(model, action):
    return f"{model._meta.app_label}.{action}_{model._meta.model_name}"


def _label(obj):
    return obj._meta.verbose_name


def _ground(place):
    """The ``Ground`` a place is, or ``None`` for a venue."""
    if place is None:
        return None
    try:
        return place.ground
    except Ground.DoesNotExist:
        return None


def _stream_body(season, title):
    """
    The YouTube ``liveStream`` resource the admin site creates for a ground
    or a season stream key (mirrors ``edit_ground`` and
    ``edit_livestreamkey`` in ``tournamentcontrol.competition.admin``).
    """
    return {
        "snippet": {"title": f"{season.competition} {season} ({title})"},
        "cdn": {
            "ingestionType": "rtmp",
            "frameRate": "variable",
            "resolution": "variable",
        },
    }


def _season_summary(season):
    return {
        "id": season.pk,
        "title": season.title,
        "short_title": season.short_title or None,
        "slug": season.slug,
        "competition": _ref(season.competition),
        "enabled": season.enabled,
        "complete": season.complete,
        "hashtag": season.hashtag or None,
        "timezone": _tzname(season.timezone),
        "start_date": season.start_date.isoformat() if season.start_date else None,
        "mode": "tournament" if season.mode == DAILY else "season",
        "statistics": season.statistics,
        "live_stream": season.live_stream,
        "live_stream_privacy": season.live_stream_privacy,
        "youtube_credentials_configured": bool(
            season.live_stream_client_id and season.live_stream_client_secret
        ),
        "youtube_authorised": bool(season.live_stream_refresh_token),
    }


def _competition_summary(competition, seasons=True):
    res = {
        "id": competition.pk,
        "title": competition.title,
        "short_title": competition.short_title or None,
        "slug": competition.slug,
        "enabled": competition.enabled,
        "clubs": [_ref(club) for club in competition.clubs.all()],
    }
    if seasons:
        res["seasons"] = [
            _season_summary(season) for season in competition.seasons.order_by("order")
        ]
    return res


def _place_summary(place):
    res = {
        "id": place.pk,
        "title": place.title,
        "short_title": place.short_title or None,
        "abbreviation": place.abbreviation or None,
        "timezone": _tzname(place.timezone),
        "latitude": float(place.latitude) if place.latitude else None,
        "longitude": float(place.longitude) if place.longitude else None,
    }
    return res


def _venue_summary(venue):
    res = _place_summary(venue)
    res["season"] = _ref(venue.season)
    res["grounds"] = [_ground_summary(g) for g in venue.grounds.order_by("order")]
    return res


def _ground_summary(ground, keys=False):
    res = _place_summary(ground)
    res["venue"] = {"id": ground.venue_id, "title": ground.venue.title}
    res["live_stream"] = ground.live_stream
    if keys:
        res["youtube_stream_id"] = ground.external_identifier or None
        res["stream_key"] = ground.stream_key or None
    return res


def _division_summary(division):
    return {
        "id": division.pk,
        "title": division.title,
        "short_title": division.short_title or None,
        "slug": division.slug,
        "season": _ref(division.season),
        "draft": division.draft,
        "points_formula": division.points_formula or None,
        "bonus_points_formula": division.bonus_points_formula or None,
        "forfeit_for_score": division.forfeit_for_score,
        "forfeit_against_score": division.forfeit_against_score,
        "include_forfeits_in_played": division.include_forfeits_in_played,
        "games_per_day": division.games_per_day,
        "stages": [_ref(stage) for stage in division.stages.order_by("order")],
        "team_count": division.teams.count(),
    }


def _team_summary(team):
    res = _team_ref(team)
    res.update(
        {
            "short_title": team.short_title or None,
            "division": _ref(team.division),
            "pool": _ref(team.stage_group),
            "timeslots_after": (
                team.timeslots_after.strftime("%H:%M") if team.timeslots_after else None
            ),
            "timeslots_before": (
                team.timeslots_before.strftime("%H:%M")
                if team.timeslots_before
                else None
            ),
            "team_clashes": [_ref(t) for t in team.team_clashes.all()],
        }
    )
    return res


def _stage_summary(stage):
    return {
        "id": stage.pk,
        "title": stage.title,
        "short_title": stage.short_title or None,
        "slug": stage.slug,
        "order": stage.order,
        "division": _ref(stage.division),
        "follows": _ref(stage.follows),
        "keep_ladder": stage.keep_ladder,
        "scale_group_points": stage.scale_group_points,
        "carry_ladder": stage.carry_ladder,
        "keep_mvp": stage.keep_mvp,
        "pools": [_pool_summary(pool) for pool in stage.pools.order_by("order")],
    }


def _pool_summary(pool):
    return {
        "id": pool.pk,
        "title": pool.title,
        "short_title": pool.short_title or None,
        "slug": pool.slug,
        "order": pool.order,
        "carry_ladder": pool.carry_ladder,
        "teams": [_team_ref(team) for team in pool.teams.order_by("order")],
        "undecided_teams": [
            {"id": t.pk, "title": t.title} for t in pool.undecided_teams.all()
        ],
    }


def _referee_summary(referee):
    return {
        "id": referee.pk,
        "name": referee.person.get_full_name,
        "person_id": str(referee.person_id),
        "club": _ref(referee.club),
    }


def _stream_key_summary(key):
    return {
        "id": key.pk,
        "title": key.title,
        "youtube_stream_id": key.external_identifier,
        "stream_key": key.stream_key,
        "events": key.live_stream_events.count(),
    }


def _stream_event_summary(event):
    tzinfo = event.season.timezone or timezone.get_current_timezone()
    return {
        "id": event.pk,
        "title": event.title,
        "description": event.description or None,
        "start": (
            timezone.localtime(event.start, tzinfo).isoformat() if event.start else None
        ),
        "stop": (
            timezone.localtime(event.stop, tzinfo).isoformat() if event.stop else None
        ),
        "live_stream": event.live_stream,
        "stream_key": (
            {"id": event.stream_key.pk, "title": event.stream_key.title}
            if event.stream_key_id
            else None
        ),
        "youtube_broadcast_id": event.external_identifier,
        "video_url": event.video_url,
    }


class AdminToolset(CompetitionToolset):
    """
    Administration tools. Every public method is published as an MCP tool
    by ``build_admin_server``; the read-only tools of ``CompetitionToolset``
    are inherited, with administrator visibility (disabled competitions and
    seasons and draft divisions included).
    """

    # -- visibility: administrators see everything ------------------------

    def _visible_competitions(self):
        return Competition.objects.all()

    def _visible_seasons(self):
        return Season.objects.select_related("competition")

    def _visible_venues(self):
        return Venue.objects.select_related("season__competition")

    def _visible_divisions(self):
        return Division.objects.select_related("season__competition")

    def _visible_teams(self):
        return Team.objects.select_related("club", "division__season__competition")

    def _visible_stages(self):
        return Stage.objects.select_related("division__season__competition")

    def _visible_matches(self, annotated=True):
        manager = Match.objects if annotated else Match._base_manager
        return manager.all()

    def _is_superuser(self):
        # Draft divisions are visible to every administrator.
        return True

    # -- authorization -------------------------------------------------------

    def _staff(self):
        user = self._user()
        if (
            user is None
            or not getattr(user, "is_authenticated", False)
            or not user.is_active
            or not user.is_staff
        ):
            raise ToolError(
                "The competition administration tools require a signed-in "
                "staff user."
            )
        return user

    def _require(self, action, model, obj=None):
        """
        Require the ``action`` permission (``add``, ``change`` or ``delete``)
        on ``model``, globally or on ``obj`` through django-guardian, as the
        admin site's ``generic_edit`` and ``generic_delete`` do.
        """
        user = self._staff()
        perm = _perm(model, action)
        if user.has_perm(perm):
            return user
        if obj is not None and obj.pk is not None and user.has_perm(perm, obj):
            return user
        raise ToolError(
            "Permission denied: %s requires the %s permission%s."
            % (
                f"{action} {_label(model)}",
                perm,
                "" if obj is None or obj.pk is None else f" for this {_label(model)}",
            )
        )

    def _require_season_access(self, season):
        """Stream keys are secrets: seeing them requires change on the season."""
        self._require("change", Season, season)

    # -- lookups -------------------------------------------------------------

    def _get(self, queryset, pk, what=None):
        model = queryset.model
        try:
            return queryset.get(pk=pk)
        except (model.DoesNotExist, ValueError, TypeError, ValidationError):
            raise ToolError(
                f"{(what or _label(model)).capitalize()} {pk} was not found."
            )

    def _competition(self, pk):
        return self._get(Competition.objects.all(), pk)

    def _season(self, pk):
        return self._get(Season.objects.select_related("competition"), pk)

    def _venue(self, pk):
        return self._get(Venue.objects.select_related("season__competition"), pk)

    def _ground_obj(self, pk):
        return self._get(
            Ground.objects.select_related("venue__season__competition"), pk
        )

    def _division(self, pk):
        return self._get(Division.objects.select_related("season__competition"), pk)

    def _team(self, pk):
        return self._get(
            Team.objects.select_related("club", "division__season__competition"), pk
        )

    def _stage(self, pk):
        return self._get(
            Stage.objects.select_related("division__season__competition"), pk
        )

    def _pool(self, pk):
        return self._get(
            StageGroup.objects.select_related("stage__division__season__competition"),
            pk,
            "pool",
        )

    def _match(self, pk):
        return self._get(
            Match.objects.select_related(
                "stage__division__season__competition",
                "stage_group",
                "play_at",
                "home_team__club",
                "away_team__club",
            ),
            pk,
        )

    def _place_obj(self, season, pk):
        """A venue of the season or one of its grounds."""
        place = self._get(
            Place.objects.filter(
                Q(venue__season=season) | Q(ground__venue__season=season)
            ).distinct(),
            pk,
            "venue or ground",
        )
        return place

    # -- forms ---------------------------------------------------------------

    def _bind(self, form_class, instance, changes, *form_args, **form_kwargs):
        """
        Bind ``form_class`` to ``instance`` with ``changes`` laid over the
        record's current values, so the form validates and saves exactly as
        a submission of the admin site's form would, without the caller
        having to repeat every field.

        A change whose value is ``None`` means "leave as is". A change to a
        field the form does not offer for this record (for example a pool
        for a stage that has none, or the slug for a user who is not a
        superuser) is refused rather than silently ignored.

        Titles, labels and names are plain text, escaped when they are
        rendered; some clients HTML-escape the arguments they relay
        ("Hit &amp; Run"), so entities in them are decoded first.
        """
        unbound = form_class(*form_args, instance=instance, **form_kwargs)
        data = {}
        for name, field in unbound.fields.items():
            self._put(data, name, field, unbound.get_initial_for_field(field, name))
        for name, value in changes.items():
            if value is None:
                continue
            if name in PLAIN_TEXT_FIELDS and isinstance(value, str):
                value = html.unescape(value)
            if name not in unbound.fields:
                raise ToolError(
                    "%s cannot be set for this %s."
                    % (name, _label(instance._meta.model))
                )
            self._put(data, name, unbound.fields[name], value)
        return form_class(*form_args, data=data, instance=instance, **form_kwargs)

    @staticmethod
    def _put(data, name, field, value):
        """
        Place ``value`` in ``data`` the way the field's widget expects to
        read it back (as a rendered form would post it): a multi-widget
        (coordinates, points formula) and the split array widget (video
        links) read one key per part, and a choice field compares against
        its prepared value (a yes/no field posts "1" or "0").
        """
        widget = field.widget
        value = field.prepare_value(value)
        if isinstance(widget, MultiWidget):
            try:
                parts = widget.decompress(value)
            except Exception as exc:
                # The points formula widget parses the formula to split it.
                raise ToolError("Validation failed: %s: %s" % (name, exc))
            for suffix, part in zip(widget.widgets_names, parts):
                data[name + suffix] = part
        elif isinstance(widget, SplitArrayWidget):
            values = list(value or [])
            for index in range(widget.size):
                data["%s_%s" % (name, index)] = (
                    values[index] if index < len(values) else ""
                )
        else:
            data[name] = value

    def _save(
        self, form_class, instance, changes, *form_args, pre_save=None, **form_kwargs
    ):
        """
        Validate and save ``instance`` through ``form_class`` (see ``_bind``).
        ``pre_save`` runs on the validated instance before it is written,
        the hook the admin site uses for its YouTube side effects.
        """
        form = self._bind(form_class, instance, changes, *form_args, **form_kwargs)
        self._validate(form)
        with transaction.atomic():
            if pre_save is not None:
                pre_save(form.instance)
            return form.save()

    @staticmethod
    def _validate(form):
        """
        Raise ``ToolError`` with the form's errors unless it is valid.

        When ``Model.clean()`` reports an error on a field the form does not
        offer (a match on a date since excluded, edited through the result
        or schedule form, whose ``date`` the model rejects) Django cannot
        attach the error to the form and raises ``ValueError`` instead; the
        model's own message is reported in that case.
        """
        try:
            valid = form.is_valid()
        except ValueError:
            try:
                form.instance.clean()
            except ValidationError as exc:
                raise ToolError("Validation failed: " + _validation_message(exc))
            raise
        if not valid:
            raise ToolError("Validation failed: " + _validation_message(form.errors))

    def _delete(self, action_label, instance):
        try:
            with transaction.atomic():
                instance.delete()
        except ProtectedError as exc:
            raise ToolError(
                "This %s cannot be deleted while other records depend on it: %s."
                % (
                    _label(instance._meta.model),
                    ", ".join(
                        sorted({_label(o._meta.model) for o in exc.protected_objects})
                    ),
                )
            )
        return {"deleted": action_label}

    # -- YouTube -------------------------------------------------------------

    @staticmethod
    def _credentials(season):
        return bool(season.live_stream_client_id and season.live_stream_client_secret)

    def _youtube(self, season):
        if not self._credentials(season):
            raise ToolError(
                "YouTube credentials must be configured for this season before "
                "live streams can be managed."
            )
        try:
            return season.youtube
        except RefreshError:
            raise ToolError(str(YOUTUBE_AUTH_EXPIRED_MESSAGE))

    @staticmethod
    def _youtube_call(request):
        try:
            return request.execute()
        except RefreshError:
            raise ToolError(str(YOUTUBE_AUTH_EXPIRED_MESSAGE))
        except HttpError as exc:
            raise ToolError("YouTube API error: %s" % exc.reason)

    def _youtube_delete(self, youtube, collection, external_identifier):
        """
        Destroy a resource on the platform; already gone is as good as
        destroyed (mirrors ``_confirm_youtube_destroyed`` in the admin).
        """
        try:
            getattr(youtube, collection)().delete(id=external_identifier).execute()
        except RefreshError:
            raise ToolError(str(YOUTUBE_AUTH_EXPIRED_MESSAGE))
        except HttpError as exc:
            if getattr(exc.resp, "status", None) != 404:
                raise ToolError("YouTube API error: %s" % exc.reason)
            logger.info("YouTube resource %r already deleted", external_identifier)
        else:
            logger.info("YouTube resource %r deleted", external_identifier)

    def _base_url(self):
        request = self.request
        if request is not None and hasattr(request, "build_absolute_uri"):
            return request.build_absolute_uri("/").rstrip("/")
        return None

    def _sync_match_live_stream(self, match):
        """
        Queue the broadcast synchronisation the admin's match edit view
        queues after saving: an existing broadcast always needs it (update
        or delete); a new one additionally needs a scheduled time.
        """
        season = match.stage.division.season
        if not self._credentials(season):
            return False
        if not match.external_identifier:
            if not match.live_stream:
                return False
            if match.get_datetime(datetime.timezone.utc) is None:
                return False
        sync_live_stream.s(match.pk, base_url=self._base_url()).apply_async()
        return True

    # ======================================================================
    # Competitions
    # ======================================================================

    def list_competitions(self) -> dict[str, Any]:
        """
        Every competition, enabled or not, with its seasons (including
        disabled and completed ones) and whether live streaming and YouTube
        credentials are configured for each season.
        """
        self._staff()
        return {
            "competitions": [
                _competition_summary(c)
                for c in Competition.objects.prefetch_related("clubs").order_by("order")
            ]
        }

    @tool_annotations()
    def create_competition(
        self,
        title: str,
        short_title: str | None = None,
        enabled: bool = True,
        copy: str | None = None,
        club_ids: list[int] | None = None,
        mysideline_url: str | None = None,
        slug: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a competition (the top of the hierarchy, for example "European
        Championships"). ``club_ids`` restricts which clubs may enter teams;
        leave it empty for a competition without clubs. ``slug`` can only be
        set by a superuser; otherwise it is derived from the title.
        """
        self._require("add", Competition)
        competition = next_related_factory(Competition)
        competition = self._save(
            CompetitionForm,
            competition,
            {
                "title": title,
                "short_title": short_title,
                "enabled": enabled,
                "copy": copy,
                "clubs": club_ids,
                "mysideline_url": mysideline_url,
                "slug": slug,
            },
            user=self._user(),
        )
        return {"saved": True, "competition": _competition_summary(competition)}

    @tool_annotations(idempotent=True)
    def update_competition(
        self,
        competition_id: int,
        title: str | None = None,
        short_title: str | None = None,
        enabled: bool | None = None,
        copy: str | None = None,
        club_ids: list[int] | None = None,
        mysideline_url: str | None = None,
        slug: str | None = None,
        slug_locked: bool | None = None,
    ) -> dict[str, Any]:
        """
        Change a competition. Only the arguments given are changed; ``club_ids``
        replaces the full list of clubs.
        """
        competition = self._competition(competition_id)
        self._require("change", Competition, competition)
        competition = self._save(
            CompetitionForm,
            competition,
            {
                "title": title,
                "short_title": short_title,
                "enabled": enabled,
                "copy": copy,
                "clubs": club_ids,
                "mysideline_url": mysideline_url,
                "slug": slug,
                "slug_locked": slug_locked,
            },
            user=self._user(),
        )
        return {"saved": True, "competition": _competition_summary(competition)}

    @tool_annotations(destructive=True)
    def delete_competition(self, competition_id: int) -> dict[str, Any]:
        """
        Delete a competition. Refused while it still has seasons.
        """
        competition = self._competition(competition_id)
        self._require("delete", Competition, competition)
        return self._delete(f"competition {competition.title}", competition)

    # ======================================================================
    # Seasons
    # ======================================================================

    @tool_annotations()
    def create_season(
        self,
        competition_id: int,
        title: str,
        short_title: str | None = None,
        timezone: str | None = None,
        start_date: datetime.date | None = None,
        mode: SeasonMode = "season",
        enabled: bool = True,
        hashtag: str | None = None,
        statistics: bool = True,
        live_stream: bool = False,
        live_stream_privacy: LiveStreamPrivacyName | None = None,
        copy: str | None = None,
        slug: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a season (one edition of a competition, for example "2026").
        ``timezone`` is an IANA name such as "Europe/Amsterdam" and is used for
        kick-off times unless a venue has its own. ``mode`` is "season" for
        a weekly competition or "tournament" for an event played over
        consecutive days. ``start_date`` prevents matches being scheduled
        earlier. Live streaming also needs YouTube credentials
        (``update_season``) and authorisation from the admin site.
        """
        competition = self._competition(competition_id)
        self._require("add", Season)
        season = next_related_factory(Season, competition)
        season = self._save(
            SeasonForm,
            season,
            {
                "title": title,
                "short_title": short_title,
                "timezone": timezone,
                "start_date": start_date,
                "mode": SEASON_MODES[mode],
                "enabled": enabled,
                "hashtag": hashtag,
                "statistics": statistics,
                "live_stream": live_stream,
                "live_stream_privacy": live_stream_privacy,
                "copy": copy,
                "slug": slug,
            },
            user=self._user(),
        )
        return {"saved": True, "season": _season_summary(season)}

    @tool_annotations(idempotent=True)
    def update_season(
        self,
        season_id: int,
        title: str | None = None,
        short_title: str | None = None,
        timezone: str | None = None,
        start_date: datetime.date | None = None,
        mode: SeasonMode | None = None,
        enabled: bool | None = None,
        complete: bool | None = None,
        hashtag: str | None = None,
        statistics: bool | None = None,
        live_stream: bool | None = None,
        live_stream_privacy: LiveStreamPrivacyName | None = None,
        live_stream_project_id: str | None = None,
        live_stream_client_id: str | None = None,
        live_stream_client_secret: str | None = None,
        copy: str | None = None,
        slug: str | None = None,
        slug_locked: bool | None = None,
    ) -> dict[str, Any]:
        """
        Change a season. Only the arguments given are changed. Marking a
        season ``complete`` stops it appearing as needing results. The
        YouTube project, client id and client secret enable live stream
        management once the season has been authorised with YouTube from
        the admin site.
        """
        season = self._season(season_id)
        self._require("change", Season, season)
        season = self._save(
            SeasonForm,
            season,
            {
                "title": title,
                "short_title": short_title,
                "timezone": timezone,
                "start_date": start_date,
                "mode": None if mode is None else SEASON_MODES[mode],
                "enabled": enabled,
                "complete": complete,
                "hashtag": hashtag,
                "statistics": statistics,
                "live_stream": live_stream,
                "live_stream_privacy": live_stream_privacy,
                "live_stream_project_id": live_stream_project_id,
                "live_stream_client_id": live_stream_client_id,
                "live_stream_client_secret": live_stream_client_secret,
                "copy": copy,
                "slug": slug,
                "slug_locked": slug_locked,
            },
            user=self._user(),
        )
        return {"saved": True, "season": _season_summary(season)}

    @tool_annotations(destructive=True)
    def delete_season(self, season_id: int) -> dict[str, Any]:
        """
        Delete a season. Refused while it still has divisions, venues or
        referees.
        """
        season = self._season(season_id)
        self._require("delete", Season, season)
        return self._delete(f"season {season.competition.title} {season.title}", season)

    # ======================================================================
    # Venues and grounds
    # ======================================================================

    def list_venues(self, season_id: int) -> dict[str, Any]:
        """
        The venues of a season with their grounds (fields, courts), time
        zones and coordinates. Use the identifiers with ``reschedule_match``
        (a match is played at a venue or at one of its grounds).
        """
        self._staff()
        season = self._season(season_id)
        return {
            "season": _ref(season),
            "venues": [
                _venue_summary(venue)
                for venue in season.venues.prefetch_related("grounds").order_by("order")
            ],
        }

    @tool_annotations()
    def create_venue(
        self,
        season_id: int,
        title: str,
        short_title: str | None = None,
        abbreviation: str | None = None,
        timezone: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        zoom: int | None = None,
        slug: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a venue in a season. ``latitude``, ``longitude`` and map
        ``zoom`` (1-20) locate it and are required; the time zone defaults to
        the season's.
        """
        season = self._season(season_id)
        self._require("add", Venue)
        venue = next_related_factory(Venue, season)
        venue.timezone = season.timezone
        venue = self._save(
            VenueForm,
            venue,
            {
                "title": title,
                "short_title": short_title,
                "abbreviation": abbreviation,
                "timezone": timezone,
                "latlng": self._latlng(venue, latitude, longitude, zoom),
                "slug": slug,
            },
            user=self._user(),
        )
        return {"saved": True, "venue": _venue_summary(venue)}

    @tool_annotations(idempotent=True)
    def update_venue(
        self,
        venue_id: int,
        title: str | None = None,
        short_title: str | None = None,
        abbreviation: str | None = None,
        timezone: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        zoom: int | None = None,
        slug: str | None = None,
        slug_locked: bool | None = None,
    ) -> dict[str, Any]:
        """
        Change a venue. Only the arguments given are changed. Changing the
        time zone recomputes the kick-off instant of its matches.
        """
        venue = self._venue(venue_id)
        self._require("change", Venue, venue)
        venue = self._save(
            VenueForm,
            venue,
            {
                "title": title,
                "short_title": short_title,
                "abbreviation": abbreviation,
                "timezone": timezone,
                "latlng": self._latlng(venue, latitude, longitude, zoom),
                "slug": slug,
                "slug_locked": slug_locked,
            },
            user=self._user(),
        )
        return {"saved": True, "venue": _venue_summary(venue)}

    @tool_annotations(destructive=True)
    def delete_venue(self, venue_id: int) -> dict[str, Any]:
        """
        Delete a venue. Refused while it still has grounds or matches.
        """
        venue = self._venue(venue_id)
        self._require("delete", Venue, venue)
        return self._delete(f"venue {venue.title}", venue)

    @staticmethod
    def _latlng(place, latitude, longitude, zoom):
        if latitude is None and longitude is None and zoom is None:
            return None
        current = (place.latlng or "").split(",") + ["", "", ""]
        parts = [
            current[0] if latitude is None else str(latitude),
            current[1] if longitude is None else str(longitude),
            current[2] if zoom is None else str(zoom),
        ]
        if not all(parts):
            raise ToolError("Give latitude, longitude and zoom together.")
        return ",".join(parts)

    @tool_annotations(open_world=True)
    def create_ground(
        self,
        venue_id: int,
        title: str,
        short_title: str | None = None,
        abbreviation: str | None = None,
        timezone: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        zoom: int | None = None,
        live_stream: bool = False,
        slug: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a ground (field, court, pitch) at a venue. It inherits the
        venue's time zone and coordinates unless given. ``live_stream`` marks
        it as a camera position, which in a live streamed season creates its
        YouTube stream and key straight away (as ``enable_ground_live_stream``
        does).
        """
        venue = self._venue(venue_id)
        self._require("add", Ground)
        ground = next_related_factory(Ground, venue, "venue")
        ground.timezone = venue.timezone
        ground.latlng = venue.latlng
        ground = self._save_ground(
            ground,
            {
                "title": title,
                "short_title": short_title,
                "abbreviation": abbreviation,
                "timezone": timezone,
                "latlng": self._latlng(ground, latitude, longitude, zoom),
                "live_stream": live_stream,
                "slug": slug,
            },
        )
        return {"saved": True, "ground": _ground_summary(ground, keys=True)}

    @tool_annotations(idempotent=True, open_world=True)
    def update_ground(
        self,
        ground_id: int,
        title: str | None = None,
        short_title: str | None = None,
        abbreviation: str | None = None,
        timezone: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        zoom: int | None = None,
        slug: str | None = None,
        slug_locked: bool | None = None,
    ) -> dict[str, Any]:
        """
        Change a ground. Only the arguments given are changed; in a live
        streamed season the title of its YouTube stream is updated too. Use
        ``enable_ground_live_stream`` / ``disable_ground_live_stream`` to
        change whether it is streamed.
        """
        ground = self._ground_obj(ground_id)
        self._require("change", Ground, ground)
        ground = self._save_ground(
            ground,
            {
                "title": title,
                "short_title": short_title,
                "abbreviation": abbreviation,
                "timezone": timezone,
                "latlng": self._latlng(ground, latitude, longitude, zoom),
                "slug": slug,
                "slug_locked": slug_locked,
            },
        )
        return {"saved": True, "ground": _ground_summary(ground, keys=True)}

    @tool_annotations(destructive=True)
    def delete_ground(self, ground_id: int) -> dict[str, Any]:
        """
        Delete a ground. Refused while matches are scheduled on it.
        """
        ground = self._ground_obj(ground_id)
        self._require("delete", Ground, ground)
        return self._delete(f"ground {ground.title}", ground)

    def _save_ground(self, ground, changes):
        """
        Save a ground through ``GroundForm`` with the YouTube ``liveStream``
        kept in step, as the admin's ``edit_ground`` does when the season is
        live streamed: a streamed ground gets a stream (and its key) created
        or its title updated, a ground no longer streamed has its stream
        removed.
        """
        season = ground.venue.season
        if not season.live_stream and not changes.get("live_stream"):
            # The form only offers the flag in a live streamed season.
            changes.pop("live_stream", None)

        def pre_save(obj):
            if not season.live_stream:
                return
            if obj.external_identifier and not obj.live_stream:
                youtube = self._youtube(season)
                self._youtube_delete(youtube, "liveStreams", obj.external_identifier)
                obj.external_identifier = None
                obj.stream_key = None
                return
            if not (obj.external_identifier or obj.live_stream):
                return
            youtube = self._youtube(season)
            body = _stream_body(season, obj.title)
            if obj.external_identifier:
                body["id"] = obj.external_identifier
                stream = self._youtube_call(
                    youtube.liveStreams().update(part="snippet,cdn", body=body)
                )
                logger.info("YouTube stream %(id)r updated", stream)
            else:
                stream = self._youtube_call(
                    youtube.liveStreams().insert(part="snippet,cdn", body=body)
                )
                obj.external_identifier = stream["id"]
                logger.info("YouTube stream %(id)r inserted", stream)
            obj.stream_key = stream["cdn"]["ingestionInfo"]["streamName"]

        return self._save(
            GroundForm, ground, changes, pre_save=pre_save, user=self._user()
        )

    # ======================================================================
    # Divisions
    # ======================================================================

    @tool_annotations()
    def create_division(
        self,
        season_id: int,
        title: str,
        short_title: str | None = None,
        draft: bool = False,
        points_formula: str | None = None,
        bonus_points_formula: str | None = None,
        forfeit_for_score: int | None = None,
        forfeit_against_score: int | None = None,
        include_forfeits_in_played: bool = True,
        games_per_day: int | None = None,
        color: str | None = None,
        copy: str | None = None,
        slug: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a division (a category contested in a season, for example
        "Men's Open"). ``draft`` hides it from the public site. The ladder
        ``points_formula`` is written with the identifiers win, draw, loss,
        bye, forfeit_for and forfeit_against, for example
        "3*win + 2*draw + 1*loss"; ``games_per_day`` only applies to
        tournament seasons.
        """
        season = self._season(season_id)
        self._require("add", Division)
        division = next_related_factory(Division, season)
        division = self._save(
            DivisionForm,
            division,
            {
                "title": title,
                "short_title": short_title,
                "draft": draft,
                "points_formula": points_formula,
                "bonus_points_formula": bonus_points_formula,
                "forfeit_for_score": forfeit_for_score,
                "forfeit_against_score": forfeit_against_score,
                "include_forfeits_in_played": include_forfeits_in_played,
                "games_per_day": games_per_day,
                "color": color,
                "copy": copy,
                "slug": slug,
            },
            user=self._user(),
        )
        return {"saved": True, "division": _division_summary(division)}

    @tool_annotations(idempotent=True)
    def update_division(
        self,
        division_id: int,
        title: str | None = None,
        short_title: str | None = None,
        draft: bool | None = None,
        points_formula: str | None = None,
        bonus_points_formula: str | None = None,
        forfeit_for_score: int | None = None,
        forfeit_against_score: int | None = None,
        include_forfeits_in_played: bool | None = None,
        games_per_day: int | None = None,
        color: str | None = None,
        copy: str | None = None,
        slug: str | None = None,
        slug_locked: bool | None = None,
    ) -> dict[str, Any]:
        """
        Change a division. Only the arguments given are changed. Changing the
        points formula recalculates every ladder of the division.
        """
        division = self._division(division_id)
        self._require("change", Division, division)
        division = self._save(
            DivisionForm,
            division,
            {
                "title": title,
                "short_title": short_title,
                "draft": draft,
                "points_formula": points_formula,
                "bonus_points_formula": bonus_points_formula,
                "forfeit_for_score": forfeit_for_score,
                "forfeit_against_score": forfeit_against_score,
                "include_forfeits_in_played": include_forfeits_in_played,
                "games_per_day": games_per_day,
                "color": color,
                "copy": copy,
                "slug": slug,
                "slug_locked": slug_locked,
            },
            user=self._user(),
        )
        return {"saved": True, "division": _division_summary(division)}

    @tool_annotations(destructive=True)
    def delete_division(self, division_id: int) -> dict[str, Any]:
        """
        Delete a division. Refused while it still has teams or stages.
        """
        division = self._division(division_id)
        self._require("delete", Division, division)
        return self._delete(f"division {division.title}", division)

    # ======================================================================
    # Teams
    # ======================================================================

    @tool_annotations()
    def create_team(
        self,
        division_id: int,
        title: str | None = None,
        club_id: int | None = None,
        short_title: str | None = None,
        copy: str | None = None,
        timeslots_after: datetime.time | None = None,
        timeslots_before: datetime.time | None = None,
        team_clash_ids: list[int] | None = None,
        slug: str | None = None,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """
        Enter a team in a division. In a competition with clubs the team
        belongs to ``club_id`` (one of the competition's clubs) and its title
        defaults to the club's; otherwise ``title`` is required. The title
        is stored as plain text ("Hit & Run"). ``timeslots_after`` /
        ``timeslots_before`` (weekly seasons only) record when the team can
        play and ``team_clash_ids`` the teams in other divisions that must
        not play at the same time (shared players), both enforced when
        scheduling. ``verbose=false`` returns just the team's id, title and
        slug.
        """
        division = self._division(division_id)
        self._require("add", Team)
        team = next_related_factory(Team, division)
        team = self._save(
            TeamForm,
            team,
            {
                "title": title,
                "club": club_id,
                "short_title": short_title,
                "copy": copy,
                "timeslots_after": timeslots_after,
                "timeslots_before": timeslots_before,
                "team_clashes": team_clash_ids,
                "slug": slug,
            },
            division,
            user=self._user(),
        )
        if not verbose:
            return {
                "saved": True,
                "team": {"id": team.pk, "title": team.title, "slug": team.slug},
            }
        return {"saved": True, "team": _team_summary(team)}

    @tool_annotations(idempotent=True)
    def update_team(
        self,
        team_id: int,
        title: str | None = None,
        club_id: int | None = None,
        short_title: str | None = None,
        copy: str | None = None,
        names_locked: bool | None = None,
        timeslots_after: datetime.time | None = None,
        timeslots_before: datetime.time | None = None,
        team_clash_ids: list[int] | None = None,
        slug: str | None = None,
        slug_locked: bool | None = None,
    ) -> dict[str, Any]:
        """
        Change a team. Only the arguments given are changed; ``team_clash_ids``
        replaces the full list. Pool membership is set with ``update_pool``.
        """
        team = self._team(team_id)
        self._require("change", Team, team)
        team = self._save(
            TeamForm,
            team,
            {
                "title": title,
                "club": club_id,
                "short_title": short_title,
                "copy": copy,
                "names_locked": names_locked,
                "timeslots_after": timeslots_after,
                "timeslots_before": timeslots_before,
                "team_clashes": team_clash_ids,
                "slug": slug,
                "slug_locked": slug_locked,
            },
            team.division,
            user=self._user(),
        )
        return {"saved": True, "team": _team_summary(team)}

    @tool_annotations(destructive=True)
    def delete_team(self, team_id: int) -> dict[str, Any]:
        """
        Withdraw a team from its division. Refused once the team has matches,
        as the admin site refuses it.
        """
        team = self._team(team_id)
        self._require("delete", Team, team)
        if team.home_games.exists() or team.away_games.exists():
            raise ToolError(
                "This team cannot be deleted because it has matches scheduled "
                "or played."
            )
        return self._delete(f"team {team.title}", team)

    # ======================================================================
    # Stages and pools
    # ======================================================================

    @tool_annotations()
    def create_stage(
        self,
        division_id: int,
        title: str,
        short_title: str | None = None,
        keep_ladder: bool = True,
        scale_group_points: bool = False,
        carry_ladder: bool = False,
        keep_mvp: bool = True,
        follows_id: int | None = None,
        color: str | None = None,
        slug: str | None = None,
    ) -> dict[str, Any]:
        """
        Add a stage to a division, after its existing stages (for example a
        "Pool Stage" followed by "Finals"). ``keep_ladder`` keeps standings
        for the stage; ``carry_ladder`` carries points over from the stage
        it ``follows`` (defaults to the previous stage).
        """
        division = self._division(division_id)
        self._require("add", Stage)
        stage = next_related_factory(Stage, division)
        stage = self._save(
            StageForm,
            stage,
            {
                "title": title,
                "short_title": short_title,
                "keep_ladder": keep_ladder,
                "scale_group_points": scale_group_points,
                "carry_ladder": carry_ladder,
                "keep_mvp": keep_mvp,
                "follows": follows_id,
                "color": color,
                "slug": slug,
            },
            user=self._user(),
        )
        return {"saved": True, "stage": _stage_summary(stage)}

    @tool_annotations(idempotent=True)
    def update_stage(
        self,
        stage_id: int,
        title: str | None = None,
        short_title: str | None = None,
        keep_ladder: bool | None = None,
        scale_group_points: bool | None = None,
        carry_ladder: bool | None = None,
        keep_mvp: bool | None = None,
        follows_id: int | None = None,
        color: str | None = None,
        slug: str | None = None,
        slug_locked: bool | None = None,
    ) -> dict[str, Any]:
        """
        Change a stage. Only the arguments given are changed.
        """
        stage = self._stage(stage_id)
        self._require("change", Stage, stage)
        stage = self._save(
            StageForm,
            stage,
            {
                "title": title,
                "short_title": short_title,
                "keep_ladder": keep_ladder,
                "scale_group_points": scale_group_points,
                "carry_ladder": carry_ladder,
                "keep_mvp": keep_mvp,
                "follows": follows_id,
                "color": color,
                "slug": slug,
                "slug_locked": slug_locked,
            },
            user=self._user(),
        )
        return {"saved": True, "stage": _stage_summary(stage)}

    @tool_annotations(destructive=True)
    def delete_stage(self, stage_id: int) -> dict[str, Any]:
        """
        Delete a stage. Refused while it still has matches or pools.
        """
        stage = self._stage(stage_id)
        self._require("delete", Stage, stage)
        return self._delete(f"stage {stage.title}", stage)

    @tool_annotations()
    def create_pool(
        self,
        stage_id: int,
        title: str,
        short_title: str | None = None,
        carry_ladder: bool = False,
        slug: str | None = None,
    ) -> dict[str, Any]:
        """
        Add a pool (group) to a stage, for example "Pool A". Place teams in it
        afterwards with ``update_pool``.
        """
        stage = self._stage(stage_id)
        self._require("add", StageGroup)
        pool = next_related_factory(StageGroup, stage)
        pool = self._save(
            StageGroupForm,
            pool,
            {
                "title": title,
                "short_title": short_title,
                "carry_ladder": carry_ladder,
                "slug": slug,
            },
            user=self._user(),
        )
        return {"saved": True, "pool": _pool_summary(pool)}

    @tool_annotations(idempotent=True)
    def update_pool(
        self,
        pool_id: int,
        title: str | None = None,
        short_title: str | None = None,
        carry_ladder: bool | None = None,
        team_ids: list[int] | None = None,
        slug: str | None = None,
        slug_locked: bool | None = None,
    ) -> dict[str, Any]:
        """
        Change a pool. ``team_ids`` sets exactly which teams of the division
        are in the pool (a team can only be in one pool per stage; in a
        later stage with no teams yet the identifiers are those of the
        stage's undecided teams). Membership can only be changed while the
        pool has no matches.
        """
        pool = self._pool(pool_id)
        self._require("change", StageGroup, pool)
        pool = self._save(
            StageGroupForm,
            pool,
            {
                "title": title,
                "short_title": short_title,
                "carry_ladder": carry_ladder,
                "teams": team_ids,
                "slug": slug,
                "slug_locked": slug_locked,
            },
            user=self._user(),
        )
        return {"saved": True, "pool": _pool_summary(pool)}

    @tool_annotations(destructive=True)
    def delete_pool(self, pool_id: int) -> dict[str, Any]:
        """
        Delete a pool. Refused while it still has matches.
        """
        pool = self._pool(pool_id)
        self._require("delete", StageGroup, pool)
        return self._delete(f"pool {pool.title}", pool)

    # ======================================================================
    # Matches
    # ======================================================================

    @tool_annotations(open_world=True)
    def create_match(
        self,
        stage_id: int,
        home_team_id: int | None = None,
        away_team_id: int | None = None,
        home_team_undecided_id: int | None = None,
        away_team_undecided_id: int | None = None,
        pool_id: int | None = None,
        round: int | None = None,
        label: str | None = None,
        date: datetime.date | None = None,
        time: datetime.time | None = None,
        place_id: int | None = None,
        include_in_ladder: bool | None = None,
        ignore_clashes: bool = False,
        home_team_eval: str | None = None,
        home_team_eval_related_id: int | None = None,
        away_team_eval: str | None = None,
        away_team_eval_related_id: int | None = None,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """
        Schedule one match in a stage. Prefer ``build_draw`` for a whole
        draw; use this for one-off matches and repairs.

        Each side is one of: a team of the division (``home_team_id``), one
        of the stage's undecided teams such as "1st Pool A"
        (``home_team_undecided_id``), or an eval decided by earlier results
        (``home_team_eval``):

        - "P1", "P2", ...: ladder position in the stage this one follows;
        - "G2P3": position 3 in pool 2 of that stage; "S1G1P2": stage 1,
          pool 1, position 2;
        - "W" or "L": winner or loser of the match given as
          ``home_team_eval_related_id``, which must be in an earlier stage
          or an earlier ``round`` of this stage.

        For example a grand final in round 14: ``home_team_eval="W"``,
        ``home_team_eval_related_id=<semi 1>``, ``away_team_eval="W"``,
        ``away_team_eval_related_id=<semi 2>``. The teams are filled in when
        the matches are progressed after the results are in.

        ``pool_id`` places the match in a pool of the stage, in which case
        both teams must be in that pool. ``date``, ``time`` and ``place_id``
        (a venue or ground) are checked with the rules of
        ``reschedule_match``; ``ignore_clashes`` waives the clash checks only,
        never excluded dates or the season's time slots.
        ``include_in_ladder`` defaults to whether the stage keeps a ladder.
        ``verbose=false`` returns just the identifiers and scheduling fields.
        """
        stage = self._stage(stage_id)
        self._require("add", Match)
        match = Match(stage=stage, include_in_ladder=stage.keep_ladder)
        changes = {
            "home_team": home_team_id,
            "away_team": away_team_id,
            "home_team_undecided": home_team_undecided_id,
            "away_team_undecided": away_team_undecided_id,
            "stage_group": pool_id,
            "round": round,
            "label": label,
            "date": date,
            "include_in_ladder": include_in_ladder,
        }
        changes.update(
            self._eval_changes(
                match,
                home_team_eval=home_team_eval,
                home_team_eval_related_id=home_team_eval_related_id,
                away_team_eval=away_team_eval,
                away_team_eval_related_id=away_team_eval_related_id,
                changes=changes,
            )
        )
        with transaction.atomic():
            # The date is validated and saved under the season lock, like
            # every other scheduling change (see _lock_seasons).
            self._lock_seasons([stage.division.season_id])
            match = self._save(AgentMatchEditForm, match, changes)
            if time is not None or place_id is not None:
                match = self._reschedule(
                    match, time=time, place_id=place_id, ignore_clashes=ignore_clashes
                )
        return {"saved": True, "match": self._match_result(match, verbose)}

    @tool_annotations(idempotent=True, open_world=True)
    def update_match(
        self,
        match_id: int,
        home_team_id: int | None = None,
        away_team_id: int | None = None,
        home_team_undecided_id: int | None = None,
        away_team_undecided_id: int | None = None,
        pool_id: int | None = None,
        round: int | None = None,
        label: str | None = None,
        include_in_ladder: bool | None = None,
        videos: list[str] | None = None,
        home_team_eval: str | None = None,
        home_team_eval_related_id: int | None = None,
        away_team_eval: str | None = None,
        away_team_eval_related_id: int | None = None,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """
        Change the teams, evals, pool, round, label, ladder inclusion or
        video links of a match. Only the arguments given are changed. Giving
        a side a team, an undecided team or an eval replaces whichever of
        the three it had (``home_team_eval=""`` clears an eval); the evals
        are those of ``create_match``. Use ``reschedule_match`` for the
        date, time and place, ``record_match_result`` for scores and
        ``set_match_referees`` for appointments. In a live streamed season
        the broadcast of a streamed match is resynchronised.
        """
        match = self._match(match_id)
        self._require("change", Match, match)
        season = match.stage.division.season
        changes = {
            "home_team": home_team_id,
            "away_team": away_team_id,
            "home_team_undecided": home_team_undecided_id,
            "away_team_undecided": away_team_undecided_id,
            "stage_group": pool_id,
            "round": round,
            "label": label,
            "include_in_ladder": include_in_ladder,
        }
        changes.update(
            self._eval_changes(
                match,
                home_team_eval=home_team_eval,
                home_team_eval_related_id=home_team_eval_related_id,
                away_team_eval=away_team_eval,
                away_team_eval_related_id=away_team_eval_related_id,
                changes=changes,
            )
        )
        if season.live_stream:
            if videos is not None:
                raise ToolError(
                    "Video links of a live streamed season are managed by the "
                    "broadcast synchronisation."
                )
            match = self._save(AgentMatchStreamForm, match, changes)
            synced = self._sync_match_live_stream(match)
        else:
            changes["videos"] = videos
            match = self._save(AgentMatchEditForm, match, changes)
            synced = False
        return {
            "saved": True,
            "live_stream_sync_queued": synced,
            "match": self._match_result(match, verbose),
        }

    @staticmethod
    def _eval_changes(match, *, changes, **evals):
        """
        Lay the eval arguments of ``create_match`` / ``update_match`` over
        ``changes``. A side is given one of a team, an undecided team or an
        eval; giving one replaces the others the match had for that side.
        """
        res = {}
        for side in ("home", "away"):
            team_eval = evals[f"{side}_team_eval"]
            related_id = evals[f"{side}_team_eval_related_id"]
            given = [
                name
                for name, value in (
                    (f"{side}_team_id", changes[f"{side}_team"]),
                    (
                        f"{side}_team_undecided_id",
                        changes[f"{side}_team_undecided"],
                    ),
                    (f"{side}_team_eval", team_eval or None),
                )
                if value is not None
            ]
            if len(given) > 1:
                raise ToolError(
                    "Give the %s side one of %s, not more than one."
                    % (side, " or ".join(given))
                )
            if team_eval is not None:
                res[f"{side}_team_eval"] = team_eval
                res[f"{side}_team_eval_related"] = related_id
                if team_eval.strip().upper() not in ("W", "L"):
                    # Only a W or L eval refers to a match: clearing the eval,
                    # or replacing it with a position, drops the reference.
                    setattr(match, f"{side}_team_eval_related", None)
            elif related_id is not None:
                res[f"{side}_team_eval_related"] = related_id
            if given:
                # The side is being replaced: forget what it had.
                keep = given[0].removeprefix(f"{side}_").removesuffix("_id")
                for attname in ("team", "team_undecided", "team_eval"):
                    if attname != keep:
                        setattr(match, f"{side}_{attname}", None)
                if keep != "team_eval":
                    setattr(match, f"{side}_team_eval_related", None)
        return res

    @tool_annotations(destructive=True)
    def delete_match(self, match_id: int) -> dict[str, Any]:
        """
        Delete a match (its ladder entries go with it). As in the admin site
        a YouTube broadcast of the match is not removed; disable its live
        stream first if it has one.
        """
        match = self._match(match_id)
        self._require("delete", Match, match)
        return self._delete(f"match {match.pk}", match)

    def _admin_match(self, match):
        match = self._match(match.pk)
        now, today = self._now()
        res = _match_summary(match, now, today)
        res.update(_place(match.play_at, detail=True))
        res["is_bye"] = match.is_bye
        res["is_forfeit"] = match.is_forfeit
        res["is_washout"] = match.is_washout
        res["bye_processed"] = match.bye_processed
        res["include_in_ladder"] = match.include_in_ladder
        res["youtube_broadcast_id"] = match.external_identifier or None
        res["referees"] = [
            _referee_summary(r) for r in match.referees.select_related("person", "club")
        ]
        return res

    def _match_result(self, match, verbose, **extra):
        """The full or compact (``verbose=False``) description of a match."""
        if verbose:
            return self._admin_match(match)
        now, today = self._now()
        res = _compact_match(match, now, today)
        res.update(extra)
        return res

    # -- scheduling ----------------------------------------------------------

    @staticmethod
    def _owner_season_id(owner):
        """The season of an exclusion date's owner (a season or division)."""
        return owner.pk if isinstance(owner, Season) else owner.season_id

    @staticmethod
    def _lock_seasons(season_ids):
        """
        Serialise scheduling within the seasons: a match has no database
        constraint against two of them taking the same place and time, so
        every tool that checks clashes and then saves holds a lock on the
        season rows (inside the caller's transaction) for the duration.
        """
        list(
            Season.objects.select_for_update()
            .filter(pk__in=set(season_ids))
            .order_by("pk")
            .values_list("pk", flat=True)
        )

    @staticmethod
    def _raise_schedule_errors(errors):
        if errors:
            raise ToolError(" ".join(errors))

    def _reschedule(
        self,
        match,
        *,
        date=None,
        time=None,
        place_id=None,
        ignore_clashes=False,
        validator=None,
        places=None,
        save=True,
        description=None,
    ):
        """
        Give ``match`` a new date, time and/or place, applying every
        scheduling rule (see ``scheduling.ScheduleValidator``): the admin
        scheduler's ``MatchScheduleForm`` checks the place and the teams'
        time preferences, the model checks the dates, the validator the
        season's time slots and the clashes. ``validator`` carries the
        places and times already handed out in a batch; ``places`` the
        season's places, to spare a batch looking them up per match.

        With ``save=False`` the validated form is returned for the caller to
        save (holding the season lock, see ``_lock_seasons``); otherwise the
        match is validated and saved under the lock.
        """
        if save:
            with transaction.atomic():
                self._lock_seasons([match.stage.division.season_id])
                # Another call may have moved the match while this one waited
                # for the lock: start from what is saved now.
                return self._reschedule(
                    self._match(match.pk),
                    date=date,
                    time=time,
                    place_id=place_id,
                    ignore_clashes=ignore_clashes,
                    validator=validator,
                    places=places,
                    save=False,
                    description=description,
                ).save()
        season = match.stage.division.season
        if validator is None:
            validator = ScheduleValidator(
                ignore_clashes=ignore_clashes, moving={match.pk}
            )
        place = None
        if place_id is not None:
            place = self._place_obj(season, place_id)
        if match.live_stream:
            ground = _ground(place if place is not None else match.play_at)
            if (
                ground is None
                or not ground.live_stream
                or not ground.external_identifier
            ):
                raise ToolError(
                    "A live streamed match can only be played on a ground that "
                    "is live streamed. Remove the live stream from the match "
                    "first, or choose a streamed ground."
                )
        if date is not None:
            match.date = date
        form = self._bind(
            MatchScheduleForm,
            match,
            {"time": time, "play_at": None if place is None else place.pk},
            ignore_clashes,
            places,
        )
        self._validate(form)
        self._raise_schedule_errors(
            validator.errors(
                form.instance,
                dates=False,  # checked by the form, through the model
                time=time is not None or date is not None,
            )
        )
        validator.claim(form.instance, description or f"match {match.pk}")
        return form

    @tool_annotations(idempotent=True, open_world=True)
    def reschedule_match(
        self,
        match_id: int,
        date: datetime.date | None = None,
        time: datetime.time | None = None,
        place_id: int | None = None,
        ignore_clashes: bool = False,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """
        Move a match: set its date, time and/or place (a venue of the season
        or one of its grounds; see ``list_venues``). Arguments left out are
        unchanged. Use ``schedule_matches`` to move many matches at once.

        The rules of the admin scheduler apply:

        - the date must not be before the season starts or on a date
          excluded for the season or the division;
        - when the season has time slot rules (``get_timeslots``) the time
          must be one of that date's slots, for example "19:00 is not a time
          slot on 2026-10-14; valid: 18:40, 19:30, 20:20";
        - the time must respect the teams' time preferences;
        - no other match may be at the same place and time that day, no team
          may play twice at the same time, and no team the sides clash with
          may play at that time.

        ``ignore_clashes`` waives the last two (the clash checks and the
        time preferences, as in the admin scheduler); it never waives an
        excluded date or the time slots. The kick-off instant is recomputed
        in the place's time zone. A match that is live streamed can only be
        moved between streamed grounds, and its broadcast is then
        resynchronised; remove the live stream first to move it elsewhere.
        ``verbose=false`` returns just the identifiers and scheduling fields.
        """
        match = self._match(match_id)
        self._require("change", Match, match)
        if date is None and time is None and place_id is None:
            raise ToolError("Give a date, time or place_id to change.")
        match = self._reschedule(
            match,
            date=date,
            time=time,
            place_id=place_id,
            ignore_clashes=ignore_clashes,
        )
        synced = self._sync_match_live_stream(match) if match.live_stream else False
        return {
            "saved": True,
            "live_stream_sync_queued": synced,
            "match": self._match_result(match, verbose),
        }

    @tool_annotations(open_world=False)
    def swap_match_allocations(
        self, match_id: int, other_match_id: int, ignore_clashes: bool = False
    ) -> dict[str, Any]:
        """
        Exchange the date, time and place of two matches of the same season
        (for example to move a game into an earlier slot). The rules of
        ``reschedule_match`` apply to each match in its new slot: excluded
        dates, time slots and, unless ``ignore_clashes``, clashes with any
        other match (a team already playing then, or a declared team
        clash). Refused if either
        match is live streamed: remove the live stream from both first
        (``disable_match_live_stream``), swap, then enable it again.
        """
        if match_id == other_match_id:
            raise ToolError("Give two different matches to swap.")
        first = self._match(match_id)
        second = self._match(other_match_id)
        self._require("change", Match, first)
        self._require("change", Match, second)
        if first.stage.division.season_id != second.stage.division.season_id:
            raise ToolError("Both matches must belong to the same season.")
        with transaction.atomic():
            # Read the slots under the lock, so a concurrent change to either
            # match is swapped from rather than overwritten.
            self._lock_seasons([first.stage.division.season_id])
            first = self._match(first.pk)
            second = self._match(second.pk)
            for match in (first, second):
                if match.live_stream:
                    raise ToolError(
                        "Match %d is live streamed; remove its live stream "
                        "before swapping its allocation." % match.pk
                    )
            first_slot = (first.date, first.time, first.play_at)
            second_slot = (second.date, second.time, second.play_at)
            first.date, first.time, first.play_at = second_slot
            second.date, second.time, second.play_at = first_slot
            # Both matches leave their current slots; each is checked in the
            # slot it takes over, against the rest of the season and the
            # other match.
            validator = ScheduleValidator(
                ignore_clashes=ignore_clashes, moving={first.pk, second.pk}
            )
            for match in (first, second):
                errors = validator.errors(match)
                validator.claim(match, f"match {match.pk}")
                if errors:
                    raise ToolError(
                        "Match %d: %s"
                        % (
                            match.pk,
                            " ".join(errors).removeprefix("Validation failed: "),
                        )
                    )
                match.save()
        return {
            "saved": True,
            "matches": [self._admin_match(first), self._admin_match(second)],
        }

    # -- referees ------------------------------------------------------------

    def list_season_referees(self, season_id: int) -> dict[str, Any]:
        """
        The referees registered for a season, with the identifiers
        ``set_match_referees`` takes. Referees are registered from the admin
        site.
        """
        self._staff()
        season = self._season(season_id)
        return {
            "season": _ref(season),
            "referees": [
                _referee_summary(r)
                for r in season.referees.select_related("person", "club")
            ],
        }

    @tool_annotations(idempotent=True)
    def set_match_referees(
        self, match_id: int, referee_ids: list[int]
    ) -> dict[str, Any]:
        """
        Appoint referees to a match: ``referee_ids`` (from
        ``list_season_referees``) replaces the current appointments; an
        empty list removes them all.
        """
        match = self._match(match_id)
        self._require("change", Match, match)
        match = self._save(MatchRefereeForm, match, {"referees": list(referee_ids)})
        return {"saved": True, "match": self._admin_match(match)}

    # -- results -------------------------------------------------------------

    def list_matches_awaiting_results(
        self,
        season_id: int | None = None,
        division_id: int | None = None,
        date: datetime.date | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Matches that have kicked off (and unprocessed byes) in seasons not
        yet complete that have no result recorded, as the admin dashboard
        lists them, oldest first; narrow by season, division or date.
        """
        self._staff()
        matches = matches_require_basic_results()
        if season_id is not None:
            matches = matches.filter(stage__division__season_id=season_id)
        if division_id is not None:
            matches = matches.filter(stage__division_id=division_id)
        if date is not None:
            matches = matches.filter(date=date)
        limit = _clamp(limit, 100, MAX_LIMIT)
        now, today = self._now()
        matches = matches.order_by("date", "time", "pk")
        return {
            "total": matches.count(),
            "matches": [
                _match_summary(match, now, today)
                for match in matches.select_related(
                    "stage__division__season__competition",
                    "stage_group",
                    "play_at",
                )[:limit]
            ],
        }

    @tool_annotations(idempotent=True)
    def record_match_result(
        self,
        match_id: int,
        home_team_score: int | None = None,
        away_team_score: int | None = None,
        is_forfeit: bool | None = None,
        forfeit_winner_id: int | None = None,
        bye_processed: bool | None = None,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """
        Enter or revise the result of a match: both scores together (home
        then away); for a forfeit set ``is_forfeit`` with the
        ``forfeit_winner_id`` (leave it out for a double forfeit) and the
        scores to record; for a bye set ``bye_processed``. The ladders are
        updated when the result is saved. ``verbose=false`` returns just the
        identifiers, scheduling fields and scores.
        """
        match = self._match(match_id)
        self._require("change", Match, match)
        match = self._save(
            MatchResultForm,
            match,
            {
                "home_team_score": home_team_score,
                "away_team_score": away_team_score,
                "is_forfeit": is_forfeit,
                "forfeit_winner": forfeit_winner_id,
                "bye_processed": bye_processed,
            },
        )
        return {
            "saved": True,
            "match": self._match_result(
                match,
                verbose,
                home_team_score=match.home_team_score,
                away_team_score=match.away_team_score,
            ),
        }

    # ======================================================================
    # Draw formats
    # ======================================================================

    def _draw_format(self, pk):
        return self._get(DrawFormat.objects.all(), pk, "draw format")

    @staticmethod
    def _parse_draw_format(text):
        """
        Validate draw format text as ``DrawFormatForm`` does and parse it,
        raising ``ToolError`` with the form's line-numbered message.
        """
        text = (text or "").strip()
        if not text:
            raise ToolError("Validation failed: text: This field is required.")
        try:
            DrawGenerator.validate(text)
        except ValueError as exc:
            raise ToolError("Validation failed: text: %s" % exc)
        generator = draw_generator(None, text)
        if not generator.rounds:
            raise ToolError(
                "Validation failed: text: The draw format has no ROUND lines."
            )
        return generator

    def list_draw_formats(
        self,
        teams: int | None = None,
        is_final: bool | None = None,
        include_text: bool = False,
    ) -> dict[str, Any]:
        """
        The saved draw formats (fixture templates; see
        ``create_draw_format``), shared by every competition. ``teams``
        lists the formats the Draw Generation wizard offers for that many
        teams: an odd number is rounded up (the extra team is a bye) and
        formats for that number or one fewer are suitable, so 7 teams match
        formats for 7 and 8 teams. ``is_final`` narrows to finals formats
        (or excludes them with false). ``include_text`` adds each format's
        text.
        """
        self._staff()
        formats = DrawFormat.objects.all()
        if teams is not None:
            formats = suitable_draw_formats(teams, formats)
        if is_final is not None:
            formats = formats.filter(is_final=is_final)
        return {
            "teams": teams,
            "draw_formats": [
                _draw_format_summary(draw_format, text=include_text)
                for draw_format in formats.order_by("teams", "name", "pk")
            ],
        }

    def get_draw_format(self, draw_format_id: int) -> dict[str, Any]:
        """
        One draw format with its text and its rounds and matches as
        structured data (see ``preview_draw_format``).
        """
        self._staff()
        draw_format = self._draw_format(draw_format_id)
        res = _draw_format_summary(draw_format)
        res["structure"] = _format_structure(
            draw_generator(None, draw_format), draw_format.teams
        )
        return {"draw_format": res}

    def preview_draw_format(
        self, text: str, teams: int | None = None
    ) -> dict[str, Any]:
        """
        Check draw format text without saving it: the same validation as
        ``create_draw_format`` (an invalid line is reported by its 0-based
        line number), then its rounds and matches as structured data (match
        id, home and away references, label). With ``teams`` it also reports
        the numbers that would be byes and how many of the possible pairings
        of that many teams the format covers. Warnings flag a team playing
        twice in a round and a W/L reference to a match that is not in an
        earlier round.
        """
        self._staff()
        return {"structure": _format_structure(self._parse_draw_format(text), teams)}

    @tool_annotations()
    def create_draw_format(
        self,
        name: str,
        text: str,
        teams: int | None = None,
        is_final: bool = False,
    ) -> dict[str, Any]:
        """
        Save a draw format: a fixture template ``build_draw`` (and the admin
        site's Draw Generation wizard) turns into matches. Formats are shared
        by every competition; ``teams`` is how many teams it is for and
        ``is_final`` marks a finals format. Check text first with
        ``preview_draw_format``.

        Syntax, one statement per line:

        - ``ROUND [label]`` starts a round, for example ``ROUND`` or
          ``ROUND Semi Finals``; every round of a draw is played on its own
          date (weekly seasons) or slot of the day (tournaments).
        - ``id: home vs away [label]`` is a match. ``id`` is a number unique
          in the format, used by W/L references; the label is optional and
          defaults to the round's label.

        Team references:

        - ``1`` .. ``n``: the n-th team of the stage or pool (in a first
          stage, the teams in their division or pool order). A number with
          no team (7 teams in an 8-team format) is a bye.
        - ``P1``: 1st on the ladder of the stage this one follows.
        - ``G1P1``: 1st of pool (group) 1 of that stage.
        - ``S1G1P2``: 2nd of pool 1 of stage 1.
        - ``W1`` / ``L1``: winner / loser of match 1 of this format, which
          must be in an earlier round.

        A round robin for 4 teams::

            ROUND
            1: 1 vs 2
            2: 3 vs 4
            ROUND
            3: 1 vs 3
            4: 2 vs 4
            ROUND
            5: 1 vs 4
            6: 2 vs 3

        Finals (top 4 of the regular season)::

            ROUND Semi Finals
            1: P1 vs P4 Semi 1
            2: P2 vs P3 Semi 2
            ROUND Grand Final
            3: W1 vs W2 Final

        Invalid text is refused with the admin form's message, naming the
        0-based numbers of the offending lines.
        """
        self._require("add", DrawFormat)
        self._parse_draw_format(text)
        draw_format = self._save(
            DrawFormatForm,
            DrawFormat(),
            {"name": name, "text": text, "teams": teams, "is_final": is_final},
        )
        return {"saved": True, "draw_format": _draw_format_summary(draw_format)}

    @tool_annotations(idempotent=True)
    def update_draw_format(
        self,
        draw_format_id: int,
        name: str | None = None,
        text: str | None = None,
        teams: int | None = None,
        is_final: bool | None = None,
    ) -> dict[str, Any]:
        """
        Change a draw format (syntax as for ``create_draw_format``). Only the
        arguments given are changed. Matches already built from it are not
        affected.
        """
        draw_format = self._draw_format(draw_format_id)
        self._require("change", DrawFormat, draw_format)
        if text is not None:
            self._parse_draw_format(text)
        draw_format = self._save(
            DrawFormatForm,
            draw_format,
            {"name": name, "text": text, "teams": teams, "is_final": is_final},
        )
        return {"saved": True, "draw_format": _draw_format_summary(draw_format)}

    @tool_annotations(destructive=True)
    def delete_draw_format(self, draw_format_id: int) -> dict[str, Any]:
        """
        Delete a draw format. Formats are shared by every competition, so
        this needs the delete permission on draw formats. Matches already
        built from the format are not affected: a draw keeps no link to the
        format it was built from.
        """
        draw_format = self._draw_format(draw_format_id)
        self._require("delete", DrawFormat, draw_format)
        return self._delete(f"draw format {draw_format.name}", draw_format)

    # ======================================================================
    # Exclusion dates
    # ======================================================================

    def _matches_on(self, matches, dates):
        now, today = self._now()
        return [
            dict(_compact_match(match, now, today), division_id=match.stage.division_id)
            for match in matches.filter(date__in=dates)
            .select_related("stage")
            .order_by("date", "time", "pk")
        ]

    def _add_exclusions(self, manager, model, owner, dates, matches):
        dates = sorted(set(dates or []))
        if not dates:
            raise ToolError("Give one or more dates to exclude.")
        self._require("add", model)
        with transaction.atomic():
            # Locking the season makes "already excluded" exact (a concurrent
            # call adding the same date waits, then sees it) and keeps a
            # scheduler from putting a match on a date being excluded.
            self._lock_seasons([self._owner_season_id(owner)])
            existing = set(
                manager.filter(date__in=dates).values_list("date", flat=True)
            )
            added = [date for date in dates if date not in existing]
            for date in added:
                manager.create(date=date)
        return {
            "saved": True,
            "added": [d.isoformat() for d in added],
            "already_excluded": [d.isoformat() for d in sorted(existing)],
            "exclusion_dates": [_exclusion_summary(e) for e in manager.all()],
            "matches_on_excluded_dates": self._matches_on(matches, dates),
        }

    def _delete_exclusions(self, manager, model, owner, dates):
        dates = sorted(set(dates or []))
        if not dates:
            raise ToolError("Give one or more dates to stop excluding.")
        self._require("delete", model)
        with transaction.atomic():
            # As when adding: under the season lock the report matches what
            # this call actually deleted.
            self._lock_seasons([self._owner_season_id(owner)])
            doomed = manager.filter(date__in=dates)
            removed = sorted(doomed.values_list("date", flat=True))
            doomed.delete()
        return {
            "deleted": [d.isoformat() for d in removed],
            "not_excluded": [d.isoformat() for d in dates if d not in removed],
            "exclusion_dates": [_exclusion_summary(e) for e in manager.all()],
        }

    def list_season_exclusion_dates(self, season_id: int) -> dict[str, Any]:
        """
        The dates excluded for a season (no matches are scheduled on them;
        ``build_draw`` skips them).
        """
        self._staff()
        season = self._season(season_id)
        return {
            "season": _ref(season),
            "exclusion_dates": [_exclusion_summary(e) for e in season.exclusions.all()],
        }

    @tool_annotations(idempotent=True)
    def add_season_exclusion_dates(
        self, season_id: int, dates: list[datetime.date]
    ) -> dict[str, Any]:
        """
        Exclude dates for every division of a season, for example a
        Christmas break: ``dates=["2026-12-23", "2026-12-30", "2027-01-06"]``.
        A date already excluded is left as it is. ``build_draw`` skips
        excluded dates and no tool will schedule a match on one. Matches
        already on an excluded date are not moved: they are listed in
        ``matches_on_excluded_dates`` for you to reschedule.
        """
        season = self._season(season_id)
        return self._add_exclusions(
            season.exclusions,
            SeasonExclusionDate,
            season,
            dates,
            Match.objects.filter(stage__division__season=season),
        )

    @tool_annotations(destructive=True)
    def delete_season_exclusion_dates(
        self, season_id: int, dates: list[datetime.date]
    ) -> dict[str, Any]:
        """
        Stop excluding dates for a season. Dates that are not excluded are
        reported in ``not_excluded``.
        """
        season = self._season(season_id)
        return self._delete_exclusions(
            season.exclusions, SeasonExclusionDate, season, dates
        )

    def list_division_exclusion_dates(self, division_id: int) -> dict[str, Any]:
        """
        The dates excluded for one division, and those excluded for its whole
        season.
        """
        self._staff()
        division = self._division(division_id)
        return {
            "division": _ref(division),
            "exclusion_dates": [
                _exclusion_summary(e) for e in division.exclusions.all()
            ],
            "season_exclusion_dates": [
                e.date.isoformat() for e in division.season.exclusions.all()
            ],
        }

    @tool_annotations(idempotent=True)
    def add_division_exclusion_dates(
        self, division_id: int, dates: list[datetime.date]
    ) -> dict[str, Any]:
        """
        Exclude dates for one division only (as ``add_season_exclusion_dates``
        does for a season). Matches of the division already on those dates
        are listed in ``matches_on_excluded_dates``, not moved.
        """
        division = self._division(division_id)
        return self._add_exclusions(
            division.exclusions,
            DivisionExclusionDate,
            division,
            dates,
            Match.objects.filter(stage__division=division),
        )

    @tool_annotations(destructive=True)
    def delete_division_exclusion_dates(
        self, division_id: int, dates: list[datetime.date]
    ) -> dict[str, Any]:
        """Stop excluding dates for a division."""
        division = self._division(division_id)
        return self._delete_exclusions(
            division.exclusions, DivisionExclusionDate, division, dates
        )

    # ======================================================================
    # Time slots
    # ======================================================================

    def _timeslot(self, pk):
        return self._get(
            SeasonMatchTime.objects.select_related("season__competition"),
            pk,
            "time slot",
        )

    def list_timeslots(self, season_id: int) -> dict[str, Any]:
        """
        The time slot rules of a season (see ``create_timeslot``); use
        ``get_timeslots`` for the kick-off times they produce.
        """
        self._staff()
        season = self._season(season_id)
        return {
            "season": _ref(season),
            "timeslots": [
                _timeslot_summary(t) for t in season.timeslots.order_by("start", "pk")
            ],
        }

    def get_timeslots(
        self, season_id: int, date: datetime.date | None = None
    ) -> dict[str, Any]:
        """
        The kick-off times a season's time slot rules produce, on ``date``
        (rules with a ``start_date`` after it or an ``end_date`` before it do
        not apply) or, without a date, from every rule. An empty list with no
        rules means any time is allowed.
        """
        self._staff()
        season = self._season(season_id)
        validator = ScheduleValidator()
        return {
            "season": _ref(season),
            "date": _iso(date),
            "rules": season.timeslots.count(),
            "times": [_hhmm(t) for t in validator.timeslots(season, date)],
        }

    @tool_annotations()
    def create_timeslot(
        self,
        season_id: int,
        start: datetime.time,
        interval: int,
        count: int,
        start_date: datetime.date | None = None,
        end_date: datetime.date | None = None,
    ) -> dict[str, Any]:
        """
        Add a time slot rule to a season: ``count`` kick-off times starting
        at ``start``, ``interval`` minutes apart. For example
        ``start="18:40", interval=50, count=3`` gives 18:40, 19:30 and 20:20.
        ``start_date`` / ``end_date`` limit the dates the rule applies to.

        Once a season has any rule, every match time must be one of the
        slots for its date (several rules add up); a season without rules
        accepts any time.
        """
        season = self._season(season_id)
        self._require("add", SeasonMatchTime)
        with transaction.atomic():
            # A time slot rule decides which times are valid: change it only
            # while no scheduling call is validating against it.
            self._lock_seasons([season.pk])
            timeslot = self._save(
                SeasonMatchTimeForm,
                SeasonMatchTime(season=season),
                {
                    "start": start,
                    "interval": interval,
                    "count": count,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
        return {
            "saved": True,
            "timeslot": _timeslot_summary(timeslot),
            "times": [
                _hhmm(t) for t in ScheduleValidator().timeslots(season, start_date)
            ],
        }

    @tool_annotations(idempotent=True)
    def update_timeslot(
        self,
        timeslot_id: int,
        start: datetime.time | None = None,
        interval: int | None = None,
        count: int | None = None,
        start_date: datetime.date | None = None,
        end_date: datetime.date | None = None,
    ) -> dict[str, Any]:
        """
        Change a time slot rule (see ``create_timeslot``). Only the arguments
        given are changed. Matches already scheduled are not moved.
        """
        timeslot = self._timeslot(timeslot_id)
        self._require("change", SeasonMatchTime, timeslot)
        with transaction.atomic():
            self._lock_seasons([timeslot.season_id])
            # Another call may have changed the rule while this one waited.
            timeslot = self._save(
                SeasonMatchTimeForm,
                self._timeslot(timeslot.pk),
                {
                    "start": start,
                    "interval": interval,
                    "count": count,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
        return {"saved": True, "timeslot": _timeslot_summary(timeslot)}

    @tool_annotations(destructive=True)
    def delete_timeslot(self, timeslot_id: int) -> dict[str, Any]:
        """
        Delete a time slot rule. When a season has no rules left any time is
        allowed again.
        """
        timeslot = self._timeslot(timeslot_id)
        self._require("delete", SeasonMatchTime, timeslot)
        with transaction.atomic():
            self._lock_seasons([timeslot.season_id])
            return self._delete(f"time slot {timeslot.pk}", timeslot)

    # ======================================================================
    # Building draws
    # ======================================================================

    def _build_plan(self, index, spec):
        """Resolve and check one ``BuildSpec`` before anything is built."""

        def fail(message):
            raise ToolError(f"build {index}: {message}")

        if (spec.stage_id is None) == (spec.pool_id is None):
            fail("give exactly one of stage_id or pool_id.")
        if (spec.draw_format_id is None) == (spec.draw_format_text is None):
            fail("give exactly one of draw_format_id or draw_format_text.")
        try:
            if spec.pool_id is not None:
                target = self._pool(spec.pool_id)
                stage, pool = target.stage, target
            else:
                target = stage = self._stage(spec.stage_id)
                pool = None
                if stage.pools.exists():
                    fail(
                        f"stage {stage.title} has pools; build each of its pools "
                        "(pool_id) instead."
                    )
            if spec.draw_format_id is not None:
                draw_format = self._draw_format(spec.draw_format_id)
                text = draw_format.text
            else:
                draw_format, text = None, spec.draw_format_text
            generator = self._parse_draw_format(text)
        except ToolError as exc:
            if str(exc).startswith(f"build {index}: "):
                raise
            fail(str(exc))

        structure = _format_structure(generator)
        for warning in structure["warnings"]:
            if "is not in an earlier round" in warning:
                fail(warning)
        season = stage.division.season
        start_date = spec.start_date or season.start_date
        if start_date is None:
            fail("give a start_date; the season has no start date.")
        teams = draw_target_team_count(target)
        if teams == 0 and structure["highest_team_number"]:
            fail(
                f"{target.title} has no teams for the format's numbered "
                "references (add teams, or place them in the pool with "
                "update_pool)."
            )
        warnings = []
        if (
            draw_format is not None
            and draw_format.teams
            and not suitable_draw_formats(teams).filter(pk=draw_format.pk).exists()
        ):
            warnings.append(
                f"Draw format {draw_format.name} is for {draw_format.teams} teams; "
                f"{target.title} has {teams}."
            )
        return {
            "index": index,
            "target": target,
            "stage": stage,
            "pool": pool,
            "draw_format": draw_format,
            "text": text,
            "spec": spec,
            "start_date": start_date,
            "warnings": warnings,
        }

    def _clear_draw(self, index, matches):
        """
        Delete the matches of a stage or pool that have no result, keeping
        those that do.
        """
        resulted = matches.filter(
            Q(home_team_score__isnull=False)
            | Q(away_team_score__isnull=False)
            | Q(is_forfeit=True)
            | Q(bye_processed=True)
        )
        kept = sorted(resulted.values_list("pk", flat=True))
        doomed = Match.objects.filter(
            pk__in=matches.exclude(pk__in=kept).values_list("pk", flat=True)
        )
        streamed = sorted(doomed.filter(live_stream=True).values_list("pk", flat=True))
        if streamed:
            raise ToolError(
                "build %d: match%s %s %s live streamed; disable the live stream "
                "before replacing the draw."
                % (
                    index,
                    "" if len(streamed) == 1 else "es",
                    ", ".join(str(pk) for pk in streamed),
                    "is" if len(streamed) == 1 else "are",
                )
            )
        deleted = doomed.count()
        # The matches being replaced may refer to each other (W/L evals).
        doomed.update(home_team_eval_related=None, away_team_eval_related=None)
        try:
            doomed.delete()
        except ProtectedError as exc:
            raise ToolError(
                "build %d: the draw cannot be replaced while other matches refer "
                "to it (W/L evals): %s."
                % (
                    index,
                    ", ".join(
                        sorted(
                            f"match {o.pk}"
                            for o in exc.protected_objects
                            if isinstance(o, Match)
                        )
                    ),
                )
            )
        return {"deleted": deleted, "kept_with_results": kept}

    @staticmethod
    def _draw_side(match, side, refs, with_ids):
        team = getattr(match, f"{side}_team")
        if team is not None:
            return {"team_id": team.pk, "title": team.title}
        undecided = getattr(match, f"{side}_team_undecided")
        if undecided is not None:
            return {"undecided_team_id": undecided.pk, "title": undecided.title}
        team_eval = getattr(match, f"{side}_team_eval")
        if team_eval:
            res = {
                "eval": team_eval,
                "title": getattr(match, f"get_{side}_team_plain")(),
            }
            related = getattr(match, f"{side}_team_eval_related")
            if related is not None:
                res["eval_ref"] = refs.get(id(related))
                if with_ids:
                    res["eval_related_id"] = related.pk
            return res
        if match.is_bye:
            return {"bye": True}
        return {"title": "TBA"}

    def _draw_rows(self, matches, refs, with_ids):
        rows = []
        for match in matches:
            row = {
                "ref": refs[id(match)],
                "round": match.round,
                "date": _iso(match.date),
                "pool_id": match.stage_group_id,
                "label": match.label or None,
                "is_bye": match.is_bye,
                "home": self._draw_side(match, "home", refs, with_ids),
                "away": self._draw_side(match, "away", refs, with_ids),
            }
            if with_ids:
                row = {"id": match.pk, **row}
            rows.append(row)
        return rows

    def _build(self, plan, *, replace_existing, dry_run, verbose):
        index, target, spec = plan["index"], plan["target"], plan["spec"]
        existing = target.matches.all()
        replaced = None
        if existing.exists():
            if not replace_existing:
                raise ToolError(
                    "build %d: %s already has %d matches; pass "
                    "replace_existing=true to replace those without results."
                    % (index, target.title, existing.count())
                )
            self._require("delete", Match)
            replaced = self._clear_draw(index, existing)

        matches = generate_stage_draw(
            target,
            plan["draw_format"] or plan["text"],
            plan["start_date"],
            spec.rounds,
            spec.offset,
            alternate_home_away_on_repeat=spec.alternate_home_away_on_repeat,
        )
        validator = ScheduleValidator()
        errors = []
        # Ladder and pool positions must resolve as Match.eval will resolve
        # them, before anything is saved or described.
        checked = {}
        for match in matches:
            for side in ("home", "away"):
                team_eval = getattr(match, f"{side}_team_eval")
                if not team_eval or team_eval in ("W", "L"):
                    continue
                if team_eval not in checked:
                    checked[team_eval] = position_eval_error(plan["stage"], team_eval)
                if checked[team_eval]:
                    errors.append(f"round {match.round}: {checked[team_eval]}")
        if errors:
            raise ToolError(f"build {index}: " + " ".join(dict.fromkeys(errors)))
        for match in matches:
            # Weekly dates come from the recurrence rule as midnight in the
            # current time zone; the match is played on that day.
            if isinstance(match.date, datetime.datetime):
                match.date = match.date.date()
            for error in validator.errors(match, time=False, clashes=False):
                errors.append(f"round {match.round} on {_iso(match.date)}: {error}")
        if errors:
            raise ToolError(f"build {index}: " + " ".join(dict.fromkeys(errors)))
        matches.save()

        refs = {id(m): f"{m.round}.{m.descriptor.match_id}" for m in matches}
        dates = [m.date for m in matches if m.date is not None]
        rounds = [m.round for m in matches]
        res = {
            "index": index,
            "stage": _ref(plan["stage"]),
            "pool": _ref(plan["pool"]),
            "draw_format": (
                _draw_format_summary(plan["draw_format"], text=False)
                if plan["draw_format"] is not None
                else None
            ),
            "start_date": _iso(plan["start_date"]),
            "matches": len(matches),
            "byes": sum(1 for m in matches if m.is_bye),
            "first_round": min(rounds, default=None),
            "last_round": max(rounds, default=None),
            "first_date": _iso(min(dates, default=None)),
            "last_date": _iso(max(dates, default=None)),
        }
        if not dry_run:
            res["match_ids"] = [m.pk for m in matches]
        if dry_run or verbose:
            res["rows"] = self._draw_rows(matches, refs, with_ids=not dry_run)
        if replaced is not None:
            res["replaced"] = replaced
        if plan["warnings"]:
            res["warnings"] = plan["warnings"]
        return res

    @tool_annotations(destructive=True)
    def build_draw(
        self,
        builds: list[BuildSpec],
        dry_run: bool = False,
        replace_existing: bool = False,
        verbose: bool = False,
    ) -> dict[str, Any]:
        """
        Build the matches of one or more stages or pools from draw formats,
        as the admin site's Draw Generation wizard does, in one atomic call
        (up to 50 builds; all are saved or none).

        Each build gives the stage (``stage_id``, a stage without pools) or
        pool (``pool_id``) to build, a format (``draw_format_id`` from
        ``list_draw_formats``, or ``draw_format_text``; see
        ``create_draw_format`` for the syntax), the ``start_date`` of the
        first round (default: the season's start date), ``rounds`` (default:
        one pass of the format; more rounds repeat it, so a 7-round format
        for 8 teams gives a 14-round double round robin with ``rounds=14``),
        an ``offset`` added to the round numbers, and
        ``alternate_home_away_on_repeat`` to swap home and away on every
        second pass through the format.

        Dates follow the season's mode: one round a week in a weekly season,
        rounds packed ``games_per_day`` to a day in a tournament, always
        skipping the season's and the division's excluded dates. Times and
        grounds are not set: use ``schedule_matches`` or ``auto_schedule``.
        Numbered references are the teams of the stage or pool; finals
        stages use P/G..P/W/L references (no teams needed), which build with
        their evals wired: a ``W1`` side refers to the match built from
        line 1, and round numbers carry on from the stage before (builds of
        earlier stages in the same call are made first, whatever their order
        in ``builds``).

        The same inputs always build the same matches. ``dry_run`` builds
        and reports the plan without saving it: for each build, ``rows``
        with each match's ``ref`` ("round.format match id"), round, date,
        pool, label and sides (a team, an undecided team, an eval with the
        ``eval_ref`` of the match it refers to, or a bye) — exactly what a
        real run saves. A real run reports per build how many matches were
        created, their ``match_ids``, rounds and date range; ``verbose``
        adds the rows, with match ids.

        A stage or pool that already has matches is refused unless
        ``replace_existing``, which deletes its matches that have no result
        (never one with a result, which is kept and reported) before
        building.

        Example: ``builds=[{"stage_id": 12, "draw_format_id": 3,
        "start_date": "2026-10-07", "rounds": 12}, {"stage_id": 13,
        "draw_format_id": 9, "start_date": "2027-01-13"}]``.
        """
        self._staff()
        if not builds:
            raise ToolError("Give one or more builds.")
        if len(builds) > MAX_BUILDS:
            raise ToolError("Give at most %d builds at once." % MAX_BUILDS)
        specs = [
            _coerce(BuildSpec, build, f"build {index}")
            for index, build in enumerate(builds)
        ]
        self._require("add", Match)
        plans = [self._build_plan(index, spec) for index, spec in enumerate(specs)]
        seen = {}
        for plan in plans:
            # A stage with pools is built pool by pool, so a stage and one of
            # its pools are never both targets.
            key = (type(plan["target"]), plan["target"].pk)
            if key in seen:
                raise ToolError(
                    "builds %d and %d build the same %s."
                    % (seen[key], plan["index"], _label(plan["target"]))
                )
            seen[key] = plan["index"]
        with transaction.atomic():
            # Without the lock two concurrent calls could both find a target
            # empty and build it twice (nothing in the database prevents it).
            self._lock_seasons(plan["stage"].division.season_id for plan in plans)
            # A later stage numbers its rounds on from the stage before it,
            # so build earlier stages first; report in the order given.
            built = {
                plan["index"]: self._build(
                    plan,
                    replace_existing=replace_existing,
                    dry_run=dry_run,
                    verbose=verbose,
                )
                for plan in sorted(
                    plans, key=lambda plan: (plan["stage"].order, plan["index"])
                )
            }
            results = [built[plan["index"]] for plan in plans]
            if dry_run:
                transaction.set_rollback(True)
        return {
            "dry_run": dry_run,
            "saved": not dry_run,
            "matches": sum(r["matches"] for r in results),
            "builds": results,
        }

    # ======================================================================
    # Batch scheduling
    # ======================================================================

    def _schedule_batch(self, entries, *, ignore_clashes, atomic, refused=False):
        """
        Validate (and, unless refused, save) a batch of ``(index, match_id,
        changes)`` entries against each other and the database. Returns the
        saved matches by index and the failures by index.

        When not ``atomic``, an entry that fails stays where it is, so the
        others are checked again against its current place until no new
        failure appears. ``refused`` validates (to report every failure)
        without saving anything.
        """
        failed = {}
        moving = {}
        seasons = set()
        for index, match_id, __ in entries:
            if match_id in moving.values():
                failed[index] = f"match {match_id} is given more than once."
                continue
            try:
                match = self._match(match_id)
                self._require("change", Match, match)
            except ToolError as exc:
                failed[index] = str(exc)
                continue
            moving[index] = match.pk
            seasons.add(match.stage.division.season_id)
        with transaction.atomic():
            self._lock_seasons(seasons)
            saved = self._schedule_locked(
                entries, failed, moving, ignore_clashes, atomic, refused
            )
        for match in saved.values():
            if match.live_stream:
                self._sync_match_live_stream(match)
        return saved, failed

    def _schedule_locked(
        self, entries, failed, moving, ignore_clashes, atomic, refused
    ):
        """The body of ``_schedule_batch``, run under the season locks."""
        places = {}
        while True:
            validator = ScheduleValidator(
                ignore_clashes=ignore_clashes,
                moving={pk for index, pk in moving.items() if index not in failed},
            )
            validator.prefetch_clashes(
                team_id
                for pair in Match.objects.filter(pk__in=moving.values()).values_list(
                    "home_team_id", "away_team_id"
                )
                for team_id in pair
            )
            forms, new_failures = {}, {}
            for index, match_id, changes in entries:
                if index in failed:
                    continue
                match = self._match(match_id)
                season_id = match.stage.division.season_id
                try:
                    form = self._reschedule(
                        match,
                        ignore_clashes=ignore_clashes,
                        validator=validator,
                        places=places.get(season_id),
                        save=False,
                        description=f"item {index} (match {match.pk})",
                        **changes,
                    )
                except ToolError as exc:
                    new_failures[index] = str(exc)
                    continue
                places.setdefault(season_id, form.fields["play_at"].queryset)
                forms[index] = form
            failed.update(new_failures)
            if atomic or not new_failures:
                break
        if refused or (atomic and failed):
            return {}
        return {index: form.save() for index, form in sorted(forms.items())}

    @staticmethod
    def _failures(failed, entries):
        match_ids = {index: match_id for index, match_id, __ in entries}
        return [
            {"index": index, "match_id": match_ids.get(index), "error": failed[index]}
            for index in sorted(failed)
        ]

    def _refuse_batch(self, failed, entries, total):
        lines = [
            "item %d (match %s): %s" % (f["index"], f["match_id"], f["error"])
            for f in self._failures(failed, entries)
        ]
        raise ToolError(
            "Nothing was scheduled: %d of %d item%s failed.\n%s"
            % (len(failed), total, "" if total == 1 else "s", "\n".join(lines))
        )

    @tool_annotations(idempotent=True, open_world=True)
    def schedule_matches(
        self,
        items: list[ScheduleItem],
        ignore_clashes: bool = False,
        atomic: bool = True,
        verbose: bool = False,
    ) -> dict[str, Any]:
        """
        Set the date, time and/or place of many matches in one call (up to
        500 items), for example a whole night or a whole season after
        ``build_draw``: ``items=[{"match_id": 451, "time": "18:40",
        "place_id": 22}, {"match_id": 452, "time": "18:40", "place_id":
        23}, ...]``. Each item takes the arguments of ``reschedule_match``
        and the same rules apply to every item: excluded dates, the season's
        time slots, the teams' time preferences, and (unless
        ``ignore_clashes``) clashes, checked against the database and
        against the other items, so two items on the same ground at the
        same time are refused.

        With ``atomic`` (the default) nothing is saved unless every item is
        valid, and the error lists every failing item by its 0-based index.
        Without it the valid items are saved and the failures reported.
        The response is compact unless ``verbose``.
        """
        self._staff()
        if not items:
            raise ToolError("Give one or more items.")
        if len(items) > MAX_SCHEDULE_ITEMS:
            raise ToolError(
                "Give at most %d items at once; split the batch." % MAX_SCHEDULE_ITEMS
            )
        entries = []
        failed = {}
        for index, item in enumerate(items):
            try:
                item = _coerce(ScheduleItem, item, f"item {index}")
            except ToolError as exc:
                failed[index] = str(exc)
                continue
            changes = {"date": item.date, "time": item.time, "place_id": item.place_id}
            if all(value is None for value in changes.values()):
                failed[index] = "give a date, time or place_id to change."
            entries.append((index, item.match_id, changes))
        saved, batch_failed = self._schedule_batch(
            [e for e in entries if e[0] not in failed],
            ignore_clashes=ignore_clashes,
            atomic=atomic,
            refused=atomic and bool(failed),
        )
        failed.update(batch_failed)
        if atomic and failed:
            self._refuse_batch(failed, entries, len(items))
        return {
            "saved": len(saved),
            "failed": self._failures(failed, entries),
            "matches": [self._match_result(match, verbose) for match in saved.values()],
        }

    @tool_annotations(idempotent=True, open_world=True)
    def auto_schedule(
        self,
        season_id: int,
        date: datetime.date,
        place_ids: list[int],
        stage_ids: list[int] | None = None,
        ignore_clashes: bool = False,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> dict[str, Any]:
        """
        Give the unscheduled matches of a season on ``date`` (those without
        a time or a place; byes are skipped) a time slot and a ground from
        ``place_ids``, optionally only those of ``stage_ids``. The season
        must have time slots (``create_timeslot``).

        The rule is deterministic: matches are taken in division, stage,
        pool, round and id order, and each takes the first free cell of the
        grid scanning the date's time slots earliest first and, within a
        slot, the places in the order of ``place_ids``. A cell that would
        break a scheduling rule for that match (a team's time preference, a
        clash) is skipped for it. Cells already used by scheduled matches
        are left alone. Matches that fit nowhere are listed in
        ``unscheduled`` with the reason. ``dry_run`` reports the assignment
        without saving it.
        """
        self._staff()
        season = self._season(season_id)
        if not place_ids:
            raise ToolError("Give the place_ids (grounds) to schedule on.")
        if len(set(place_ids)) != len(place_ids):
            raise ToolError("Each place may be given only once.")
        places = [self._place_obj(season, place_id) for place_id in place_ids]
        # Hold the season lock from reading the time slots and free cells
        # until they are saved, so a concurrent scheduler (or a change to the
        # time slots) cannot invalidate them.
        with transaction.atomic():
            self._lock_seasons([season.pk])
            validator = ScheduleValidator(ignore_clashes=ignore_clashes)
            if not validator.has_timeslot_rules(season):
                raise ToolError(
                    "auto_schedule fills the season's time slots and this season "
                    "has none; add them with create_timeslot, or give the times "
                    "with schedule_matches."
                )
            slots = validator.timeslots(season, date)
            if not slots:
                raise ToolError(
                    "The season has no time slots on %s." % date.isoformat()
                )
            matches = Match.objects.filter(
                stage__division__season=season, date=date, is_bye=False
            ).filter(Q(time__isnull=True) | Q(play_at__isnull=True))
            if stage_ids:
                matches = matches.filter(stage_id__in=stage_ids)
            matches = list(
                matches.order_by(
                    "stage__division__order",
                    "stage__order",
                    F("stage_group__order").asc(nulls_first=True),
                    "round",
                    "pk",
                )
            )
            validator.moving = {match.pk for match in matches}
            validator.prefetch_clashes(
                team_id
                for match in matches
                for team_id in (match.home_team_id, match.away_team_id)
            )
            occupied = set(
                Match.objects.filter(date=date, play_at__in=places, time__in=slots)
                .exclude(pk__in=validator.moving)
                .values_list("time", "play_at_id")
            )
            cells = [
                (time, place)
                for time in slots
                for place in places
                if (time, place.pk) not in occupied
            ]
            forms = []
            unscheduled = []
            choices = None
            for candidate in matches:
                self._require("change", Match, candidate)
                reason = "every time slot and place is taken."
                for cell in list(cells):
                    time, place = cell
                    try:
                        form = self._reschedule(
                            self._match(candidate.pk),
                            time=time,
                            place_id=place.pk,
                            ignore_clashes=ignore_clashes,
                            validator=validator,
                            places=choices,
                            save=False,
                        )
                    except ToolError as exc:
                        reason = str(exc)
                        continue
                    choices = form.fields["play_at"].queryset
                    cells.remove(cell)
                    forms.append(form)
                    break
                else:
                    unscheduled.append({"match_id": candidate.pk, "reason": reason})
            with transaction.atomic():
                saved = [form.save() for form in forms]
                if dry_run:
                    transaction.set_rollback(True)
        if not dry_run:
            for match in saved:
                if match.live_stream:
                    self._sync_match_live_stream(match)
        now, today = self._now()
        return {
            "dry_run": dry_run,
            "date": date.isoformat(),
            "time_slots": [_hhmm(t) for t in slots],
            "scheduled": len(saved),
            "matches": [
                (
                    _compact_match(match, now, today)
                    if dry_run or not verbose
                    else self._admin_match(match)
                )
                for match in saved
            ],
            "unscheduled": unscheduled,
        }

    # ======================================================================
    # Live streaming
    # ======================================================================

    def list_season_stream_keys(self, season_id: int) -> dict[str, Any]:
        """
        The stream keys of a season that are not tied to a ground: the pool
        used by ad-hoc live stream events, each with its YouTube stream id,
        the key itself and how many events use it. Requires change
        permission on the season.
        """
        season = self._season(season_id)
        self._require_season_access(season)
        return {
            "season": _ref(season),
            "stream_keys": [
                _stream_key_summary(key) for key in season.live_stream_keys.all()
            ],
        }

    def list_season_stream_events(self, season_id: int) -> dict[str, Any]:
        """
        The ad-hoc live stream events of a season (broadcasts that are not
        a match, such as an opening ceremony), with their times in the
        season's time zone, the stream key each uses and the video link.
        """
        self._staff()
        season = self._season(season_id)
        return {
            "season": _ref(season),
            "events": [
                _stream_event_summary(event)
                for event in season.live_stream_events.select_related(
                    "season", "stream_key"
                ).order_by("start", "pk")
            ],
        }

    def list_streamed_grounds(self, season_id: int) -> dict[str, Any]:
        """
        The grounds of a season that are live streamed (camera positions),
        each with its YouTube stream id and stream key and how many upcoming
        matches on it are being streamed. Requires change permission on the
        season.
        """
        season = self._season(season_id)
        self._require_season_access(season)
        now, __ = self._now()
        grounds = []
        for ground in (
            Ground.objects.filter(venue__season=season, live_stream=True)
            .select_related("venue")
            .order_by("venue__order", "order")
        ):
            res = _ground_summary(ground, keys=True)
            res["upcoming_streamed_matches"] = self._streamed_usages(
                ground, now
            ).count()
            grounds.append(res)
        return {"season": _ref(season), "grounds": grounds}

    @staticmethod
    def _streamed_usages(ground, now):
        return Match.objects.filter(play_at=ground, live_stream=True).filter(
            Q(datetime__gte=now) | Q(datetime__isnull=True)
        )

    @tool_annotations(open_world=True)
    def create_season_stream_key(self, season_id: int, title: str) -> dict[str, Any]:
        """
        Create a stream key for ad-hoc events in a live streamed season,
        titled for the camera or production position that will use it. The
        stream is created on YouTube, so the season needs credentials and
        authorisation.
        """
        season = self._season(season_id)
        self._require("add", LiveStreamKey)
        if not season.live_stream:
            raise ToolError("Live streaming is not enabled for this season.")
        youtube = self._youtube(season)

        def pre_save(obj):
            stream = self._youtube_call(
                youtube.liveStreams().insert(
                    part="snippet,cdn", body=_stream_body(season, obj.title)
                )
            )
            obj.external_identifier = stream["id"]
            obj.stream_key = stream["cdn"]["ingestionInfo"]["streamName"]
            logger.info("YouTube stream %(id)r inserted", stream)

        key = self._save(
            LiveStreamKeyForm,
            LiveStreamKey(season=season),
            {"title": title},
            pre_save=pre_save,
        )
        return {"saved": True, "stream_key": _stream_key_summary(key)}

    @tool_annotations(destructive=True, open_world=True)
    def delete_season_stream_key(
        self, season_id: int, stream_key_id: str
    ) -> dict[str, Any]:
        """
        Delete an ad-hoc stream key of a season (``stream_key_id`` is the
        ``id`` from ``list_season_stream_keys``). Refused while any live
        stream event still uses it. The stream is removed from YouTube
        first; one already gone counts as removed.
        """
        season = self._season(season_id)
        key = self._get(season.live_stream_keys.all(), stream_key_id, "stream key")
        self._require("delete", LiveStreamKey, key)
        used_by = key.live_stream_events.count()
        if used_by:
            raise ToolError(
                "This stream key is used by %d live stream event%s; reassign or "
                "delete them first." % (used_by, "" if used_by == 1 else "s")
            )
        youtube = self._youtube(season)
        self._youtube_delete(youtube, "liveStreams", key.external_identifier)
        return self._delete(f"stream key {key.title}", key)

    @tool_annotations(open_world=True)
    def enable_ground_live_stream(self, ground_id: int) -> dict[str, Any]:
        """
        Make a ground a live streamed camera position: a YouTube stream is
        created for it and its stream key returned for the camera operator.
        The season must have live streaming enabled with YouTube credentials.
        """
        ground = self._ground_obj(ground_id)
        self._require("change", Ground, ground)
        season = ground.venue.season
        if not season.live_stream:
            raise ToolError("Live streaming is not enabled for this season.")
        if ground.live_stream:
            raise ToolError("This ground is already live streamed.")
        self._youtube(season)
        ground = self._save_ground(ground, {"live_stream": True})
        return {"saved": True, "ground": _ground_summary(ground, keys=True)}

    @tool_annotations(destructive=True, open_world=True)
    def disable_ground_live_stream(self, ground_id: int) -> dict[str, Any]:
        """
        Stop live streaming from a ground and remove its YouTube stream and
        key. Refused while any upcoming match on the ground is set to be
        live streamed; disable those first.
        """
        ground = self._ground_obj(ground_id)
        self._require("change", Ground, ground)
        if not ground.live_stream:
            raise ToolError("This ground is not live streamed.")
        now, __ = self._now()
        usages = self._streamed_usages(ground, now).count()
        if usages:
            raise ToolError(
                "%d upcoming match%s on this ground %s set to be live streamed; "
                "disable their live streams first."
                % (usages, "" if usages == 1 else "es", "is" if usages == 1 else "are")
            )
        if ground.external_identifier:
            self._youtube(ground.venue.season)
        ground = self._save_ground(ground, {"live_stream": False})
        return {"saved": True, "ground": _ground_summary(ground, keys=True)}

    @tool_annotations(open_world=True)
    def enable_match_live_stream(self, match_id: int) -> dict[str, Any]:
        """
        Schedule the live stream of a match. The match must be played on a
        ground that is live streamed (has a stream key) in a season with live
        streaming enabled; its YouTube broadcast is created and bound to the
        ground's stream when the season has credentials.
        """
        match = self._match(match_id)
        self._require("change", Match, match)
        season = match.stage.division.season
        if not season.live_stream:
            raise ToolError("Live streaming is not enabled for this season.")
        if match.live_stream:
            raise ToolError("This match is already set to be live streamed.")
        ground = _ground(match.play_at)
        if ground is None or not ground.live_stream or not ground.external_identifier:
            raise ToolError(
                "This match is not scheduled on a live streamed ground. Move it "
                "to a ground with a stream key (see list_streamed_grounds) or "
                "enable live streaming on its ground first."
            )
        match = self._save(MatchStreamForm, match, {"live_stream": True})
        synced = self._sync_match_live_stream(match)
        return {
            "saved": True,
            "live_stream_sync_queued": synced,
            "match": self._admin_match(match),
        }

    @tool_annotations(destructive=True, open_world=True)
    def disable_match_live_stream(self, match_id: int) -> dict[str, Any]:
        """
        Withdraw the live stream of a match that is set to be streamed; its
        YouTube broadcast is removed when the season has credentials.
        """
        match = self._match(match_id)
        self._require("change", Match, match)
        if not match.live_stream:
            raise ToolError("This match is not set to be live streamed.")
        match = self._save(MatchStreamForm, match, {"live_stream": False})
        synced = self._sync_match_live_stream(match)
        return {
            "saved": True,
            "live_stream_sync_queued": synced,
            "match": self._admin_match(match),
        }


def build_admin_server(name=None, instructions=None):
    """
    Build the administration ``MCPServer``: the project's own instructions,
    then the administration instructions, then the schedule and results
    instructions the read tools are described by.
    """
    combined = ADMIN_INSTRUCTIONS
    if instructions:
        combined = instructions.strip() + "\n\n" + combined
    server = build_server(
        name=name or "tournamentcontrol-admin",
        instructions=combined,
        toolset_class=AdminToolset,
    )
    return server


_server = None


def get_admin_server():
    """
    The process-wide administration server configured from
    ``TOURNAMENTCONTROL_MCP_ADMIN_NAME`` and
    ``TOURNAMENTCONTROL_MCP_ADMIN_INSTRUCTIONS`` (falling back to the
    ``TOURNAMENTCONTROL_MCP_INSTRUCTIONS`` of the public server).
    """
    global _server
    if _server is None:
        _server = build_admin_server(
            name=getattr(settings, "TOURNAMENTCONTROL_MCP_ADMIN_NAME", None),
            instructions=getattr(
                settings,
                "TOURNAMENTCONTROL_MCP_ADMIN_INSTRUCTIONS",
                getattr(settings, "TOURNAMENTCONTROL_MCP_INSTRUCTIONS", None),
            ),
        )
    return _server
