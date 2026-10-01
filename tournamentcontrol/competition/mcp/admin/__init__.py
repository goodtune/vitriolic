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
import logging
from typing import Any, Literal

from dateutil.rrule import DAILY, WEEKLY
from django.conf import settings
from django.contrib.postgres.forms import SplitArrayWidget
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.forms.widgets import MultiWidget
from django.utils import timezone
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from mcp.server.mcpserver.exceptions import ToolError

from tournamentcontrol.competition.admin import (
    YOUTUBE_AUTH_EXPIRED_MESSAGE,
    next_related_factory,
)
from tournamentcontrol.competition.dashboard import (
    matches_require_basic_results,
)
from tournamentcontrol.competition.forms import (
    CompetitionForm,
    DivisionForm,
    GroundForm,
    LiveStreamKeyForm,
    MatchEditForm,
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
    _match_summary,
    _place,
    _ref,
    _team_ref,
    _tzname,
    build_server,
    tool_annotations,
)
from tournamentcontrol.competition.models import (
    Competition,
    Division,
    Ground,
    LiveStreamKey,
    Match,
    Place,
    Season,
    Stage,
    StageGroup,
    Team,
    Venue,
)
from tournamentcontrol.competition.tasks import sync_live_stream

logger = logging.getLogger(__name__)

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
and `create_pool` (teams are placed in pools with `update_pool`), and finally
`create_match`. Use the read tools (`search`, `get_season`, `list_teams`,
`list_matches`, `get_match`, `get_ladder`) to find identifiers and to confirm
each step; as an administrator you also see disabled competitions and draft
divisions.

Scheduling: `reschedule_match` sets the date, time and place (venue or
ground) of one match and applies the same rules as the admin scheduler
(season start and excluded dates, team time preferences, time-and-place and
team clashes unless `ignore_clashes`). `swap_match_allocations` exchanges the
date, time and place of two matches. Neither will move a match that is
being live streamed; remove the live stream first.

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

Every tool that changes data reports the record as saved. A tool that cannot
proceed (missing permission, a rule such as "the stream key is in use", or a
validation failure) returns an error explaining why.
""".strip()


def _perm(model, action):
    return f"{model._meta.app_label}.{action}_{model._meta.model_name}"


def _label(obj):
    return obj._meta.verbose_name


def _validation_message(errors):
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
        """
        unbound = form_class(*form_args, instance=instance, **form_kwargs)
        data = {}
        for name, field in unbound.fields.items():
            self._put(data, name, field, unbound.get_initial_for_field(field, name))
        for name, value in changes.items():
            if value is None:
                continue
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
    ) -> dict[str, Any]:
        """
        Enter a team in a division. In a competition with clubs the team
        belongs to ``club_id`` (one of the competition's clubs) and its title
        defaults to the club's; otherwise ``title`` is required.
        ``timeslots_after`` / ``timeslots_before`` (weekly seasons only)
        record when the team can play and ``team_clash_ids`` the teams in
        other divisions that must not play at the same time (shared
        players), both enforced when scheduling.
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
    ) -> dict[str, Any]:
        """
        Schedule a match in a stage between two teams of the division (or
        two of the stage's undecided teams, such as "1st Pool A", in a
        later stage). ``pool_id`` places it in a pool of the stage, in which
        case both teams must be in that pool. ``date``, ``time`` and
        ``place_id`` (a venue or ground) are applied with the scheduling
        rules of ``reschedule_match``. ``include_in_ladder`` defaults to
        whether the stage keeps a ladder.
        """
        stage = self._stage(stage_id)
        self._require("add", Match)
        match = Match(stage=stage, include_in_ladder=stage.keep_ladder)
        with transaction.atomic():
            match = self._save(
                MatchEditForm,
                match,
                {
                    "home_team": home_team_id,
                    "away_team": away_team_id,
                    "home_team_undecided": home_team_undecided_id,
                    "away_team_undecided": away_team_undecided_id,
                    "stage_group": pool_id,
                    "round": round,
                    "label": label,
                    "date": date,
                    "include_in_ladder": include_in_ladder,
                },
            )
            if time is not None or place_id is not None:
                match = self._reschedule(
                    match, time=time, place_id=place_id, ignore_clashes=ignore_clashes
                )
        return {"saved": True, "match": self._admin_match(match)}

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
    ) -> dict[str, Any]:
        """
        Change the teams, pool, round, label, ladder inclusion or video links
        of a match. Only the arguments given are changed. Use
        ``reschedule_match`` for the date, time and place,
        ``record_match_result`` for scores and ``set_match_referees`` for
        appointments. In a live streamed season the broadcast of a streamed
        match is resynchronised.
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
        if season.live_stream:
            if videos is not None:
                raise ToolError(
                    "Video links of a live streamed season are managed by the "
                    "broadcast synchronisation."
                )
            match = self._save(MatchStreamForm, match, changes)
            synced = self._sync_match_live_stream(match)
        else:
            changes["videos"] = videos
            match = self._save(MatchEditForm, match, changes)
            synced = False
        return {
            "saved": True,
            "live_stream_sync_queued": synced,
            "match": self._admin_match(match),
        }

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

    # -- scheduling ----------------------------------------------------------

    def _check_clashes(self, match, play_at, time):
        """
        The clash rules of the admin scheduler's ``MatchScheduleFormSet``
        applied to one match: no other match at the same place and time on
        the day, and none of the teams' declared clashes playing at the same
        time.
        """
        others = (
            Match.objects.filter(date=match.date)
            .exclude(pk=match.pk)
            .exclude(play_at=None, time=None)
        )
        if play_at is not None and time is not None:
            if others.filter(play_at=play_at, time=time).exists():
                raise ToolError(
                    "Another match is already scheduled for this time & place."
                )
        if time is not None:
            for team in (match.home_team, match.away_team):
                if team is None:
                    continue
                for clash in team.team_clashes.all():
                    if others.filter(
                        Q(home_team=clash) | Q(away_team=clash), time=time
                    ).exists():
                        raise ToolError(
                            "%s must not play at the same time as %s (%s), who "
                            "are already scheduled at %s."
                            % (
                                team.title,
                                clash.title,
                                clash.division.title,
                                time.strftime("%H:%M"),
                            )
                        )

    def _reschedule(
        self, match, *, date=None, time=None, place_id=None, ignore_clashes=False
    ):
        season = match.stage.division.season
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
        )
        self._validate(form)
        if not ignore_clashes:
            self._check_clashes(
                match, form.cleaned_data.get("play_at"), form.cleaned_data.get("time")
            )
        with transaction.atomic():
            match = form.save()
        return match

    @tool_annotations(idempotent=True, open_world=True)
    def reschedule_match(
        self,
        match_id: int,
        date: datetime.date | None = None,
        time: datetime.time | None = None,
        place_id: int | None = None,
        ignore_clashes: bool = False,
    ) -> dict[str, Any]:
        """
        Move a match: set its date, time and/or place (a venue of the season
        or one of its grounds; see ``list_venues``). Arguments left out are
        unchanged. The rules of the admin scheduler apply: the date must not
        be before the season starts or on a date excluded for the season or
        division; the time must respect the teams' time preferences; and,
        unless ``ignore_clashes``, no other match may be at the same place
        and time that day and no team the sides clash with may play at that
        time. The kick-off instant is recomputed in the place's time zone. A
        match that is live streamed can only be moved between streamed
        grounds, and its broadcast is then resynchronised; remove the live
        stream first to move it elsewhere.
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
            "match": self._admin_match(match),
        }

    @tool_annotations(open_world=False)
    def swap_match_allocations(
        self, match_id: int, other_match_id: int
    ) -> dict[str, Any]:
        """
        Exchange the date, time and place of two matches of the same season
        (for example to move a game into an earlier slot). Refused if either
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
        for match in (first, second):
            if match.live_stream:
                raise ToolError(
                    "Match %d is live streamed; remove its live stream before "
                    "swapping its allocation." % match.pk
                )
        first_slot = (first.date, first.time, first.play_at)
        second_slot = (second.date, second.time, second.play_at)
        first.date, first.time, first.play_at = second_slot
        second.date, second.time, second.play_at = first_slot
        with transaction.atomic():
            for match in (first, second):
                try:
                    match.clean()
                except ValidationError as exc:
                    raise ToolError(
                        "Match %d: %s" % (match.pk, _validation_message(exc))
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
    ) -> dict[str, Any]:
        """
        Enter or revise the result of a match: both scores together (home
        then away); for a forfeit set ``is_forfeit`` with the
        ``forfeit_winner_id`` (leave it out for a double forfeit) and the
        scores to record; for a bye set ``bye_processed``. The ladders are
        updated when the result is saved.
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
        return {"saved": True, "match": self._admin_match(match)}

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
