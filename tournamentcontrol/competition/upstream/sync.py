"""
Reconcile a Season with the competitions its upstream provider publishes.

The provider is authoritative. Each synchronisation fetches a complete
snapshot of every relevant competition *before* touching the database, then
converges the local models onto that snapshot inside a single transaction:

* remote entities that are new locally are created;
* remote entities that already exist locally (matched on their stable
  qualified ``upstream_id``) have their externally-managed fields updated,
  including renames, rescheduling, pool membership and results;
* local entities that carry an ``upstream_id`` but no longer exist remotely
  are removed. Where a removal is blocked because native Vitriolic data
  depends on the record, the record is detached from the provider (its
  identifier cleared, or the division marked as draft) instead of failing
  the whole synchronisation.

Anything that does not carry an ``upstream_id`` is never touched, so native
divisions, teams and matches can coexist with synchronised ones.

The one thing the provider is *not* authoritative for is the name of a
division or team. Upstream naming is often unwieldy -- "Born 2014 & 2013 u14
Boys" for what is better published as "14 Boys" -- so a title changed by an
administrator is kept, while the remote name continues to be recorded so
that a later upstream rename is reported rather than silently discarded. See
:class:`~tournamentcontrol.competition.models.UpstreamMixin`.

Mapping of the provider-neutral snapshot onto Vitriolic models:

=================  ======================================================
Snapshot           Vitriolic
=================  ======================================================
organisation       ``Competition`` (``Competition.upstream_url``)
season page        ``Season`` (``Season.upstream_url`` selects which of the
                   organisation's competitions belong to the season)
competition        ``Division`` (``Division.upstream_id``)
round type         ``Stage`` -- "Regular" rounds and "Final" rounds each
                   map onto a stage of the division
pool               ``StageGroup`` on the regular stage, matched by name
team               ``Team`` (``Team.upstream_id``)
match              ``Match`` (``Match.upstream_id``)
venue / field      ``Venue`` / ``Ground`` (matched by title, created when
                   absent; these are shared with native data and never
                   removed by the synchronisation)
=================  ======================================================
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.db.models import Max, ProtectedError, Q
from django.utils.text import slugify

from tournamentcontrol.competition.models import (
    Division,
    Ground,
    Match,
    Season,
    Stage,
    StageGroup,
    Team,
    UndecidedTeam,
    Venue,
)
from tournamentcontrol.competition.upstream.base import (
    HttpClient,
    UpstreamProvider,
)
from tournamentcontrol.competition.upstream.types import (
    STATUS_FINAL,
    RemoteCompetition,
    RemoteLadderTemplate,
    RemoteMatch,
)

logger = logging.getLogger(__name__)

REGULAR_STAGE_TITLE = "Regular Season"
FINALS_STAGE_TITLE = "Finals"
TBA_LABEL = "TBA"

# Applied when a division is *created* by the synchronisation, from the
# competition's ladder template when the provider could supply one and
# otherwise from the "TFA Standard Ladder" defaults. Ladder configuration
# is not overwritten on later syncs, so administrators may change it.
DEFAULT_LADDER_TEMPLATE = RemoteLadderTemplate()
DEFAULT_FORFEIT_AGAINST_SCORE = 0


@dataclass
class SyncResult:
    """Counts of what a synchronisation did, for logging and reporting."""

    created: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)
    deleted: dict[str, int] = field(default_factory=dict)
    detached: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def _bump(self, bucket: dict[str, int], model) -> None:
        name = model._meta.model_name if hasattr(model, "_meta") else str(model)
        bucket[name] = bucket.get(name, 0) + 1

    def add_created(self, obj) -> None:
        self._bump(self.created, obj)

    def add_updated(self, obj) -> None:
        self._bump(self.updated, obj)

    def add_deleted(self, obj) -> None:
        self._bump(self.deleted, obj)

    def add_detached(self, obj) -> None:
        self._bump(self.detached, obj)

    def warn(self, message: str, *args) -> None:
        logger.warning(message, *args)
        self.warnings.append(message % args if args else message)

    def summary(self) -> str:
        def fmt(bucket):
            return ", ".join("%s=%d" % kv for kv in sorted(bucket.items())) or "-"

        return "created: %s; updated: %s; deleted: %s; detached: %s" % (
            fmt(self.created),
            fmt(self.updated),
            fmt(self.deleted),
            fmt(self.detached),
        )


def _provider(season: Season) -> UpstreamProvider:
    if not season.competition.upstream_url:
        raise ValueError("Competition %r has no upstream_url" % season.competition)
    if not season.upstream_url:
        raise ValueError("Season %r has no upstream_url" % season)
    provider = season.upstream_provider
    if provider is None:
        raise ValueError(
            "Competition %r upstream_url is not on a supported provider"
            % season.competition
        )
    return provider


def fetch_snapshot(
    season: Season, client: Optional[HttpClient] = None
) -> list[RemoteCompetition]:
    """
    Fetch the complete remote snapshot for a season without touching the
    database. Any transport or parsing error propagates; a partial snapshot
    is never returned.
    """
    return _provider(season).fetch_snapshot(season, client)


def synchronise_season(
    season: Season, client: Optional[HttpClient] = None
) -> SyncResult:
    """
    Synchronise ``season`` with its upstream provider.

    Raises :class:`~tournamentcontrol.competition.upstream.base.UpstreamError`
    (or a subclass) if the remote data cannot be obtained; in that case the
    local data is left untouched.
    """
    provider = _provider(season)
    snapshots = provider.fetch_snapshot(season, client)
    result = apply_snapshot(season, snapshots)
    logger.info("%s sync of %r: %s", provider.name, season, result.summary())
    return result


@transaction.atomic
def apply_snapshot(season: Season, snapshots: list[RemoteCompetition]) -> SyncResult:
    """
    Converge ``season`` onto ``snapshots`` in a single transaction.

    Separated from :func:`synchronise_season` so that the reconciliation can
    be exercised (and tested) independently of the HTTP layer.
    """
    result = SyncResult()
    reconciler = _SeasonReconciler(season, _provider(season), result)
    reconciler.apply(snapshots)
    return result


def _next_order(queryset) -> int:
    return (queryset.aggregate(order=Max("order"))["order"] or 0) + 1


def _unique_slug(queryset, title: str, exclude_pk=None) -> str:
    """
    Slugify ``title`` and, when another object in ``queryset`` already uses
    that slug, suffix it ("-2", "-3", ...). Distinct remote names such as
    "Men's 55s" and "Mens 55s" otherwise collide.
    """
    base = slugify(title) or "untitled"
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    slug, suffix = base, 2
    while queryset.filter(slug=slug).exists():
        slug = "%s-%d" % (base, suffix)
        suffix += 1
    return slug


def _set_attrs(obj, result: SyncResult, **attrs) -> bool:
    """Assign ``attrs`` to ``obj``; return whether anything changed."""
    changed = []
    for name, value in attrs.items():
        if getattr(obj, name) != value:
            setattr(obj, name, value)
            changed.append(name)
    if changed:
        obj.save()
        result.add_updated(obj)
    return bool(changed)


def _slug_attrs(obj, title: str, siblings) -> dict:
    if obj.slug_locked and obj.slug:
        return {}
    if obj.slug and obj.slug.startswith(slugify(title)):
        # Keep an existing (possibly suffixed) slug for an unchanged title.
        return {}
    return {"slug": _unique_slug(siblings, title, exclude_pk=obj.pk)}


def _title_attrs(obj, remote_name: str, siblings, result: SyncResult) -> dict:
    """
    Reconcile ``obj.title`` with the name the provider currently publishes.

    The remote name is always recorded in ``upstream_title``, whether or not
    we use it. It is *applied* only while our title still matches the remote
    name it was last reconciled with: a title an administrator has changed
    is kept, and a remote rename of such a record is reported instead of
    being silently discarded. Saving the record in the admin reconciles it
    again, either accepting the remote name or acknowledging the remote
    change while keeping ours.
    """
    attrs = {"upstream_title": remote_name}
    label = obj._meta.verbose_name

    if obj.upstream_title_overridden:
        if obj.upstream_title_synced != remote_name:
            result.warn(
                "%s %r (%s) was renamed remotely from %r to %r; "
                "the local name is kept.",
                label.capitalize(),
                obj.title,
                obj.upstream_id,
                obj.upstream_title_synced,
                remote_name,
            )
        return attrs

    if (
        obj.title != remote_name
        and siblings.exclude(pk=obj.pk).filter(title__iexact=remote_name).exists()
    ):
        # Two records cannot share a name; leave this one alone and try
        # again next time, by which point the other may have moved on.
        result.warn(
            "%s %r (%s) cannot be renamed to %r because another "
            "%s of the same name exists; left in place.",
            label.capitalize(),
            obj.title,
            obj.upstream_id,
            remote_name,
            label,
        )
        return attrs

    attrs["title"] = remote_name
    attrs["upstream_title_synced"] = remote_name
    attrs.update(_slug_attrs(obj, remote_name, siblings))
    return attrs


def _remove(obj, result: SyncResult) -> bool:
    """
    Delete ``obj`` if nothing protects it. Returns ``True`` on deletion.
    """
    try:
        with transaction.atomic():
            obj.delete()
    except ProtectedError:
        return False
    result.add_deleted(obj)
    return True


def _remove_stage(stage: Stage, result: SyncResult) -> bool:
    """
    Delete ``stage`` along with the "TBA" placeholders the synchronisation
    created for it, if nothing native protects it.
    """
    try:
        with transaction.atomic():
            for tba in stage.undecided_teams.filter(label=TBA_LABEL, formula=""):
                tba.delete()
            stage.delete()
    except ProtectedError:
        return False
    result.add_deleted(stage)
    return True


def _remove_team(team: Team, result: SyncResult) -> bool:
    """
    Delete ``team`` if nothing native protects it.

    Ladder summaries are derived from matches and are regenerated whenever a
    match is saved, so they are cleared first rather than allowed to protect
    the team; registrations and native matches do protect it.
    """
    try:
        with transaction.atomic():
            team.ladder_summary.all().delete()
            team.delete()
    except ProtectedError:
        return False
    result.add_deleted(team)
    return True


class _SeasonReconciler:
    def __init__(self, season: Season, provider: UpstreamProvider, result: SyncResult):
        self.season = season
        self.provider = provider
        self.result = result

    # -- season ------------------------------------------------------------

    def apply(self, snapshots: list[RemoteCompetition]) -> None:
        existing = {
            division.upstream_id: division
            for division in self.season.divisions.filter(upstream_id__isnull=False)
        }
        for snapshot in snapshots:
            upstream_id = self.provider.identifier(snapshot.id)
            division = existing.pop(upstream_id, None)
            if division is None:
                division = self._adopt_or_create_division(snapshot, upstream_id)
            _DivisionReconciler(self, division, snapshot).apply()
        for division in existing.values():
            self._remove_division(division)

    def _adopt_or_create_division(
        self, snapshot: RemoteCompetition, upstream_id: str
    ) -> Division:
        # A division created by hand with the same title is adopted rather
        # than duplicated; this lets an administrator pre-configure ladder
        # settings before linking a season to the provider.
        division = self.season.divisions.filter(
            upstream_id__isnull=True, title__iexact=snapshot.name
        ).first()
        if division is not None:
            division.upstream_id = upstream_id
            division.upstream_title = snapshot.name
            # Adoption asserts that this division *is* the remote one, so its
            # title counts as reconciled; any difference in case is applied
            # by the normal title reconciliation.
            division.upstream_title_synced = division.title
            division.save(
                update_fields=["upstream_id", "upstream_title", "upstream_title_synced"]
            )
            self.result.add_updated(division)
            logger.info("Adopted division %r as %s", division, upstream_id)
            return division
        template = snapshot.ladder_template or DEFAULT_LADDER_TEMPLATE
        division = Division(
            season=self.season,
            title=snapshot.name,
            slug=_unique_slug(self.season.divisions, snapshot.name),
            order=_next_order(self.season.divisions),
            upstream_id=upstream_id,
            upstream_title=snapshot.name,
            upstream_title_synced=snapshot.name,
            points_formula=template.points_formula,
            forfeit_for_score=template.forfeit_score,
            forfeit_against_score=DEFAULT_FORFEIT_AGAINST_SCORE,
            include_forfeits_in_played=template.forfeit_counts_as_played,
        )
        division.save()
        self.result.add_created(division)
        for warning in snapshot.warnings:
            self.result.warn(
                "Division %r (%s): %s", division.title, upstream_id, warning
            )
        return division

    def _remove_division(self, division: Division) -> None:
        """
        The competition no longer exists upstream. Remove everything the
        provider owned within the division and then the division itself; if
        native data protects any of it, keep the division but mark it as
        draft so it is hidden from the public site.
        """
        blocked = False
        for match in Match.objects.filter(
            stage__division=division, upstream_id__isnull=False
        ):
            blocked |= not _remove(match, self.result)
        for team in division.teams.filter(upstream_id__isnull=False):
            if not _remove_team(team, self.result):
                blocked = True
                _set_attrs(team, self.result, upstream_id=None)
                self.result.add_detached(team)
        if not blocked:
            for stage in division.stages.order_by("-order"):
                for pool in stage.pools.all():
                    blocked |= not _remove(pool, self.result)
                blocked |= not _remove_stage(stage, self.result)
        if not blocked and _remove(division, self.result):
            return
        self.result.warn(
            "Division %r (%s) no longer exists remotely but could not be "
            "deleted because native data depends on it; marked as draft.",
            division.title,
            division.upstream_id,
        )
        _set_attrs(division, self.result, draft=True)
        self.result.add_detached(division)


class _DivisionReconciler:
    def __init__(
        self, parent: _SeasonReconciler, division: Division, snapshot: RemoteCompetition
    ):
        self.season = parent.season
        self.provider = parent.provider
        self.result = parent.result
        self.division = division
        self.snapshot = snapshot
        self.teams: dict[str, Team] = {}
        self.pools: dict[str, StageGroup] = {}
        self.regular_stage: Optional[Stage] = None
        self.finals_stage: Optional[Stage] = None
        self._tba: dict[int, UndecidedTeam] = {}
        self._venues: dict[str, Venue] = {}
        self._grounds: dict[tuple[int, str], Ground] = {}

    def apply(self) -> None:
        _set_attrs(
            self.division,
            self.result,
            **_title_attrs(
                self.division,
                self.snapshot.name,
                self.season.divisions,
                self.result,
            ),
        )
        self.regular_stage = self._stage(REGULAR_STAGE_TITLE, 1)
        self._reconcile_pools()
        self._reconcile_teams()
        self._reconcile_matches()

    # -- stages & pools ----------------------------------------------------

    def _stage(self, title: str, order: int, keep_ladder: bool = True) -> Stage:
        stage = self.division.stages.filter(title=title).first()
        if stage is None:
            stage = Stage(
                division=self.division,
                title=title,
                slug=slugify(title),
                order=max(order, _next_order(self.division.stages)),
                keep_ladder=keep_ladder,
            )
            stage.save()
            self.result.add_created(stage)
        return stage

    def _reconcile_pools(self) -> None:
        existing = {pool.title: pool for pool in self.regular_stage.pools.all()}
        for name in self.snapshot.pools:
            pool = existing.pop(name, None)
            if pool is None:
                pool = StageGroup(
                    stage=self.regular_stage,
                    title=name,
                    slug=slugify(name),
                    order=_next_order(self.regular_stage.pools),
                )
                pool.save()
                self.result.add_created(pool)
            self.pools[name] = pool
        # Pools are keyed by name (providers expose no pool identifier), so
        # a pool that disappears remotely is removed locally once nothing
        # references it any more; matches are reconciled before that check
        # happens in the next sync, so a renamed pool converges in two runs.
        self._stale_pools = list(existing.values())

    def _finish_pools(self) -> None:
        for pool in self._stale_pools:
            pool.teams.update(stage_group=None)
            if not _remove(pool, self.result):
                self.result.warn(
                    "Pool %r in %r no longer exists upstream but is still "
                    "referenced by native matches; left in place.",
                    pool.title,
                    self.division.title,
                )

    # -- teams -------------------------------------------------------------

    def _reconcile_teams(self) -> None:
        local = {
            team.upstream_id: team
            for team in self.division.teams.filter(upstream_id__isnull=False)
        }
        for remote in self.snapshot.teams:
            pool = self.pools.get(remote.pool) if remote.pool else None
            upstream_id = self.provider.identifier(remote.id)
            team = local.pop(upstream_id, None)
            if team is None:
                team = self._adopt_or_create_team(upstream_id, remote.name, pool)
            _set_attrs(
                team,
                self.result,
                division_id=self.division.pk,
                stage_group_id=pool.pk if pool else None,
                **_title_attrs(team, remote.name, self.division.teams, self.result),
            )
            self.teams[remote.id] = team
        for team in local.values():
            self._remove_team(team)

    def _adopt_or_create_team(
        self, upstream_id: str, name: str, pool: Optional[StageGroup]
    ) -> Team:
        # The identifier is globally unique, so a team may already exist in
        # another division (eg. moved between competitions remotely).
        team = Team.objects.filter(upstream_id=upstream_id).first()
        if team is not None:
            return team
        team = self.division.teams.filter(
            upstream_id__isnull=True, title__iexact=name
        ).first()
        if team is not None:
            team.upstream_id = upstream_id
            team.upstream_title = name
            # See _adopt_or_create_division.
            team.upstream_title_synced = team.title
            team.save(
                update_fields=["upstream_id", "upstream_title", "upstream_title_synced"]
            )
            self.result.add_updated(team)
            logger.info("Adopted team %r as %s", team, upstream_id)
            return team
        team = Team(
            division=self.division,
            title=name,
            slug=_unique_slug(self.division.teams, name),
            order=_next_order(self.division.teams),
            stage_group=pool,
            upstream_id=upstream_id,
            upstream_title=name,
            upstream_title_synced=name,
        )
        team.save()
        self.result.add_created(team)
        return team

    def _remove_team(self, team: Team) -> None:
        # Matches owned by the provider that reference the team are removed
        # first (they cannot exist remotely if the team does not). Native
        # matches referencing it will block the delete; detach instead.
        for match in Match.objects.filter(
            Q(home_team=team) | Q(away_team=team), upstream_id__isnull=False
        ):
            _remove(match, self.result)
        if _remove_team(team, self.result):
            return
        self.result.warn(
            "Team %r in %r no longer exists upstream but is referenced by "
            "native matches; detached from %s.",
            team.title,
            self.division.title,
            self.provider.name,
        )
        _set_attrs(team, self.result, upstream_id=None)
        self.result.add_detached(team)

    # -- matches -----------------------------------------------------------

    def _reconcile_matches(self) -> None:
        if any(match.is_final_round for match in self.snapshot.matches):
            # Finals are an elimination series, so the finals stage keeps no
            # ladder. Like the points formula this only applies on creation.
            self.finals_stage = self._stage(FINALS_STAGE_TITLE, 2, keep_ladder=False)

        local = {
            match.upstream_id: match
            for match in Match.objects.filter(
                stage__division=self.division, upstream_id__isnull=False
            )
        }
        for remote in self.snapshot.matches:
            upstream_id = self.provider.identifier(remote.id)
            match = local.pop(upstream_id, None)
            if match is None:
                match = Match.objects.filter(upstream_id=upstream_id).first()
            if match is None:
                match = Match(upstream_id=upstream_id)
                created = True
            else:
                created = False
            self._apply_match(match, remote, created)
        for match in local.values():
            _remove(match, self.result)

        self._finish_pools()

        # A finals stage created by an earlier sync whose fixtures have all
        # been withdrawn remotely is removed once it is empty.
        if self.finals_stage is None:
            stale = self.division.stages.filter(title=FINALS_STAGE_TITLE).first()
            if stale is not None and not stale.matches.exists():
                _remove_stage(stale, self.result)

    def _apply_match(self, match: Match, remote: RemoteMatch, created: bool) -> None:
        home = self.teams.get(remote.home_team_id) if remote.home_team_id else None
        away = self.teams.get(remote.away_team_id) if remote.away_team_id else None

        stage = self.finals_stage if remote.is_final_round else self.regular_stage
        pool_id = None
        if stage is self.regular_stage and home is not None and away is not None:
            if home.stage_group_id and home.stage_group_id == away.stage_group_id:
                pool_id = home.stage_group_id

        tzinfo = self._tzinfo(remote)
        local_dt = remote.start.astimezone(tzinfo) if remote.start else None
        play_at = self._play_at(remote)

        # Foreign keys are compared and assigned by id so that a Ground
        # (a Place subclass) is not reported as differing from the Place
        # instance the relation returns.
        # A fixture whose participants are yet to be determined (typically a
        # final before the regular season is complete) is represented with a
        # placeholder "TBA" undecided team so that it renders sensibly.
        tba = None
        if not remote.is_bye and (home is None or away is None):
            tba = self._tba_team(stage)

        attrs = dict(
            stage_id=stage.pk,
            stage_group_id=pool_id,
            round=remote.round_number,
            label=remote.round_name if remote.is_final_round else None,
            home_team_id=home.pk if home else None,
            away_team_id=away.pk if away else None,
            home_team_undecided_id=tba.pk if tba and home is None else None,
            away_team_undecided_id=tba.pk if tba and away is None else None,
            date=local_dt.date() if local_dt else None,
            time=local_dt.time() if local_dt and remote.has_time else None,
            datetime=local_dt if local_dt and remote.has_time else None,
            play_at_id=play_at.pk if play_at else None,
            is_bye=remote.is_bye,
            bye_processed=remote.is_bye and remote.status == STATUS_FINAL,
        )
        attrs.update(self._result_attrs(remote, home, away))

        if created:
            for name, value in attrs.items():
                setattr(match, name, value)
            match.save()
            self.result.add_created(match)
        else:
            _set_attrs(match, self.result, **attrs)

    def _tba_team(self, stage: Stage) -> UndecidedTeam:
        tba = self._tba.get(stage.pk)
        if tba is None:
            tba = stage.undecided_teams.filter(label=TBA_LABEL, formula="").first()
        if tba is None:
            tba = UndecidedTeam(stage=stage, label=TBA_LABEL)
            tba.save()
            self.result.add_created(tba)
        self._tba[stage.pk] = tba
        return tba

    def _result_attrs(self, remote: RemoteMatch, home, away) -> dict:
        if remote.is_forfeit and (home is not None or away is not None):
            division = self.division
            forfeit_for = division.forfeit_for_score
            forfeit_against = division.forfeit_against_score
            if remote.forfeiting_team_id == remote.home_team_id and away is not None:
                winner, home_score, away_score = away, forfeit_against, forfeit_for
            elif remote.forfeiting_team_id == remote.away_team_id and home is not None:
                winner, home_score, away_score = home, forfeit_for, forfeit_against
            else:
                winner, home_score, away_score = None, forfeit_against, forfeit_against
            return dict(
                is_forfeit=True,
                forfeit_winner_id=winner.pk if winner else None,
                home_team_score=home_score,
                away_team_score=away_score,
            )
        if remote.has_result:
            return dict(
                is_forfeit=False,
                forfeit_winner_id=None,
                home_team_score=remote.home_score,
                away_team_score=remote.away_score,
            )
        return dict(
            is_forfeit=False,
            forfeit_winner_id=None,
            home_team_score=None,
            away_team_score=None,
        )

    def _tzinfo(self, remote: RemoteMatch):
        if remote.venue and remote.venue.timezone:
            try:
                return ZoneInfo(remote.venue.timezone)
            except (ZoneInfoNotFoundError, ValueError):
                pass
        if self.season.timezone:
            return self.season.timezone
        return ZoneInfo("UTC")

    # -- venues ------------------------------------------------------------

    def _play_at(self, remote: RemoteMatch):
        if remote.venue is None:
            return None
        venue = self._venue(remote)
        if remote.field:
            return self._ground(venue, remote.field)
        return venue

    def _venue(self, remote: RemoteMatch) -> Venue:
        key = remote.venue.name.lower()
        venue = self._venues.get(key)
        if venue is None:
            venue = self.season.venues.filter(title__iexact=remote.venue.name).first()
        if venue is None:
            latlng = ""
            if remote.venue.latitude is not None and remote.venue.longitude is not None:
                latlng = "%s,%s,15" % (remote.venue.latitude, remote.venue.longitude)
            venue = Venue(
                season=self.season,
                title=remote.venue.name,
                slug=slugify(remote.venue.name),
                order=_next_order(self.season.venues),
                latlng=latlng,
                timezone=self._venue_timezone(remote),
            )
            venue.save()
            self.result.add_created(venue)
        self._venues[key] = venue
        return venue

    def _ground(self, venue: Venue, field_no: str) -> Ground:
        title = field_no if not field_no.isdigit() else "Field %s" % field_no
        key = (venue.pk, title.lower())
        ground = self._grounds.get(key)
        if ground is None:
            ground = venue.grounds.filter(title__iexact=title).first()
        if ground is None:
            ground = Ground(
                venue=venue,
                title=title,
                slug=slugify(title),
                order=_next_order(venue.grounds),
                latlng=venue.latlng,
                timezone=venue.timezone,
            )
            ground.save()
            self.result.add_created(ground)
        self._grounds[key] = ground
        return ground

    def _venue_timezone(self, remote: RemoteMatch):
        if remote.venue.timezone:
            try:
                return ZoneInfo(remote.venue.timezone)
            except (ZoneInfoNotFoundError, ValueError):
                pass
        return self.season.timezone


def linked_seasons():
    """Enabled, incomplete seasons linked to an upstream provider."""
    return (
        Season.objects.filter(
            enabled=True,
            complete=False,
            upstream_url__isnull=False,
            competition__upstream_url__isnull=False,
        )
        .exclude(upstream_url="")
        .exclude(competition__upstream_url="")
        .select_related("competition")
    )


def synchronise_all(clients: Optional[dict] = None) -> dict[int, SyncResult]:
    """
    Synchronise every enabled, incomplete season that names an upstream URL
    within a competition that has one.

    ``clients`` optionally maps a provider key to the client to use for that
    provider (the tests pass canned sessions this way). Failures are
    isolated per season: a season whose remote data cannot be fetched is
    logged and skipped, the others still synchronise.
    """
    clients = dict(clients or {})
    results = {}
    for season in linked_seasons():
        provider = season.upstream_provider
        if provider is None:
            logger.warning(
                "Season %r is linked to an unsupported upstream URL %r",
                season,
                season.competition.upstream_url,
            )
            continue
        client = clients.get(provider.key)
        if client is None:
            client = clients[provider.key] = provider.new_client()
        try:
            results[season.pk] = synchronise_season(season, client)
        except Exception:
            logger.exception("%s sync of %r failed", provider.name, season)
    return results


__all__ = [
    "SyncResult",
    "apply_snapshot",
    "fetch_snapshot",
    "linked_seasons",
    "synchronise_all",
    "synchronise_season",
]
