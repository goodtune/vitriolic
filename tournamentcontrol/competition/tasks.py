import base64
import logging
from zoneinfo import ZoneInfo

import requests
from celery import Task, shared_task, states
from dateutil.relativedelta import relativedelta
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from google.auth.exceptions import RefreshError
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from googleapiclient.errors import HttpError

from tournamentcontrol.competition.models import (
    LiveStreamEvent,
    Match,
    Season,
    Stage,
)
from tournamentcontrol.competition.mysideline.sync import (
    synchronise_all as _mysideline_synchronise_all,
    synchronise_season as _mysideline_synchronise_season,
)
from tournamentcontrol.competition.utils import (
    generate_fixture_grid,
    generate_scorecards,
)

logger = logging.getLogger(__name__)

# YouTube broadcast duration. A match window covers warm-up, play, and a
# trailing buffer; tighten or widen here if competitions need a different
# default. Per-season overrides would belong on the Season model.
LIVE_STREAM_DURATION_MINUTES = 50

# The remote PDF service occasionally times out or answers with a 5xx. Retry
# those renders a couple of times, waiting PDF_RENDER_RETRY_DELAY seconds
# before the first retry and doubling the wait for each one after it.
PDF_RENDER_MAX_RETRIES = 2
PDF_RENDER_RETRY_DELAY = 3


class _ShortTitle:
    """Substitute ``short_title`` for the rendered name of a SitemapNodeBase.

    Both ``str(obj)`` and attribute access via ``obj.title`` return the short
    form when set, falling back to ``title``. All other attributes are
    forwarded to the wrapped object so templates can still resolve fields
    like ``slug`` or ``short_title`` directly.
    """

    def __init__(self, obj):
        self.__dict__["_obj"] = obj

    def __str__(self):
        if self._obj is None:
            return ""
        return self._obj.short_title or self._obj.title

    @property
    def title(self):
        if self._obj is None:
            return ""
        return self._obj.short_title or self._obj.title

    def __getattr__(self, name):
        return getattr(self._obj, name)


def build_live_stream_body(match, base_url=None, short=False, label_only=False):
    """Render title/description templates and build the YouTube broadcast body.

    Returns the body dict, or ``None`` if the match lacks a scheduled start time.

    When ``short`` is true, ``short_title`` is substituted for ``title`` on
    Competition/Season/Division/Stage in the rendered title and description.

    ``label_only`` is passed to the templates, where a true value asks the
    title of a match that has a label ("Gold Medal") to leave its teams out.
    It makes no difference to a match without a label, whose title has
    nothing but its teams to tell it apart.
    """
    stage = match.stage
    division = stage.division
    season = division.season
    competition = season.competition

    if short:
        ctx_division = _ShortTitle(division)
        ctx_season = _ShortTitle(season)
        ctx_competition = _ShortTitle(competition)
        ctx_stage = _ShortTitle(stage)
    else:
        ctx_division = division
        ctx_season = season
        ctx_competition = competition
        ctx_stage = stage

    # Default to an empty string rather than ``None`` so a missing URL doesn't
    # render as the literal "None" in the YouTube description template.
    match_url = ""
    if base_url and match.pk is not None:
        try:
            relative = reverse(
                "competition:match-video",
                kwargs={
                    "competition": competition.slug,
                    "season": season.slug,
                    "division": division.slug,
                    "match": match.pk,
                },
            )
            match_url = base_url.rstrip("/") + relative
        except NoReverseMatch:
            match_url = ""

    template_context = {
        "match": match,
        "competition": ctx_competition,
        "season": ctx_season,
        "division": ctx_division,
        "stage": ctx_stage,
        "match_url": match_url,
        "label_only": label_only,
    }

    title_templates = [
        f"tournamentcontrol/competition/{stage.slug}/{division.slug}/{season.slug}/{competition.slug}/match/live_stream/title.txt",
        f"tournamentcontrol/competition/{stage.slug}/{division.slug}/{season.slug}/match/live_stream/title.txt",
        f"tournamentcontrol/competition/{stage.slug}/{division.slug}/match/live_stream/title.txt",
        f"tournamentcontrol/competition/{stage.slug}/match/live_stream/title.txt",
        "tournamentcontrol/competition/match/live_stream/title.txt",
    ]
    title = render_to_string(title_templates, template_context).strip()

    description_templates = [
        f"tournamentcontrol/competition/{stage.slug}/{division.slug}/{season.slug}/{competition.slug}/match/live_stream/description.txt",
        f"tournamentcontrol/competition/{stage.slug}/{division.slug}/{season.slug}/match/live_stream/description.txt",
        f"tournamentcontrol/competition/{stage.slug}/{division.slug}/match/live_stream/description.txt",
        f"tournamentcontrol/competition/{stage.slug}/match/live_stream/description.txt",
        "tournamentcontrol/competition/match/live_stream/description.txt",
    ]
    description = render_to_string(description_templates, template_context).strip()

    start_time = match.get_datetime(ZoneInfo("UTC"))
    if start_time is None:
        return None

    stop_time = start_time + relativedelta(minutes=LIVE_STREAM_DURATION_MINUTES)

    return {
        "snippet": {
            "title": title,
            "description": description,
            "scheduledStartTime": start_time.isoformat(),
            "scheduledEndTime": stop_time.isoformat(),
        },
        "status": {
            "privacyStatus": season.live_stream_privacy,
            "selfDeclaredMadeForKids": False,
        },
        "contentDetails": {
            "enableAutoStart": False,
            "enableAutoStop": False,
            "monitorStream": {
                "broadcastStreamDelayMs": 0,
                "enableMonitorStream": True,
            },
        },
    }


# The forms a match's broadcast title is offered to YouTube in, from the most
# to the least descriptive, as the ``short`` and ``label_only`` arguments of
# ``build_live_stream_body``.
_TITLE_FORMS = (
    (False, False),
    (True, False),
    (False, True),
    (True, True),
)


def _is_title_too_long(exc):
    """Return True when an HttpError indicates an exceeded title length.

    YouTube reports a title over its limit as ``invalidTitle`` ("Title is
    invalid") without saying that length was the reason, so any rejection of
    the title counts; a shorter form of the title is the only remedy there
    is to try.
    """
    content = getattr(exc, "content", b"") or b""
    if isinstance(content, (bytes, bytearray)):
        content = bytes(content).decode("utf-8", errors="replace")
    needle = str(content).lower()
    if "title" not in needle:
        return False
    return any(
        marker in needle
        for marker in (
            "too long",
            "maxlength",
            "max length",
            "invalidvalue",
            "invalidtitle",
        )
    )


def _get_ground(place):
    """Return the Ground subclass instance for ``place``, or ``None``.

    ``Place`` is the parent of ``Ground`` via multi-table inheritance, so
    accessing ``place.ground`` raises ``Ground.DoesNotExist`` (a subclass of
    ``ObjectDoesNotExist``) when the ``Place`` isn't actually a ``Ground``.
    """
    if place is None:
        return None
    try:
        return place.ground
    except (AttributeError, ObjectDoesNotExist):
        return None


def _apply_sync(match, season, body):
    """Apply a single insert/update/delete + bind cycle against YouTube.

    ``body`` may be ``None`` for the delete path, which doesn't need a rendered
    broadcast body. Returns what was done to the broadcast: ``"created"``,
    ``"updated"`` or ``"removed"``.
    """
    youtube = season.youtube
    action = "updated"
    if match.external_identifier:
        if not match.live_stream:
            video_id = match.external_identifier
            youtube.liveBroadcasts().delete(id=video_id).execute()
            videos = list(match.videos or [])
            link = f"https://youtu.be/{video_id}"
            if link in videos:
                videos.remove(link)
            match.external_identifier = None
            match.videos = videos or None
            match.live_stream_bind = None
            match.save(
                update_fields=["external_identifier", "videos", "live_stream_bind"]
            )
            logger.info("YouTube video %r deleted", video_id)
            return "removed"

        body["id"] = match.external_identifier
        youtube.liveBroadcasts().update(
            part="snippet,status,contentDetails", body=body
        ).execute()
        logger.info("YouTube video %r updated", match.external_identifier)
    elif match.live_stream:
        broadcast = (
            youtube.liveBroadcasts()
            .insert(part="id,snippet,status,contentDetails", body=body)
            .execute()
        )
        match.external_identifier = broadcast["id"]
        link = f"https://youtu.be/{match.external_identifier}"
        videos = list(match.videos or [])
        videos.append(link)
        match.videos = videos
        match.save(update_fields=["external_identifier", "videos"])
        logger.info("YouTube video %r inserted", match.external_identifier)
        action = "created"

    ground = _get_ground(match.play_at)
    if match.external_identifier and ground and ground.external_identifier:
        bind = (
            youtube.liveBroadcasts()
            .bind(
                part="id,snippet,contentDetails,status",
                id=match.external_identifier,
                streamId=ground.external_identifier,
            )
            .execute()
        )
        bound = bind["contentDetails"].get("boundStreamId")
        if bound != match.live_stream_bind:
            match.live_stream_bind = bound
            match.save(update_fields=["live_stream_bind"])
    elif match.external_identifier and match.live_stream_bind:
        # The match no longer plays on a ground with a stream; calling bind
        # without a streamId removes the existing binding.
        youtube.liveBroadcasts().bind(
            part="id,snippet,contentDetails,status",
            id=match.external_identifier,
        ).execute()
        match.live_stream_bind = None
        match.save(update_fields=["live_stream_bind"])
    return action


@shared_task
def sync_live_stream(match_pk, base_url=None):
    """Synchronize a match with its YouTube broadcast.

    Creates, updates, deletes, and binds the live broadcast as required by the
    current state of the match. When YouTube rejects the title (it allows 100
    characters) the next shorter form is tried, so a recoverable failure
    remains non-fatal and the broadcast can still be created: first with
    shortened titles (using ``short_title`` on Division, Season, Competition,
    and Stage where set), then, for a match that has a label, without its
    teams ("Men's 50 | Gold Medal | ..."), and last both together. Every
    synchronisation starts again from the full title, so a later one (once
    the teams of a final are known, say) restores the fullest form that fits.

    The match row is locked for the duration, so concurrent synchronisations
    (a queued run and a resync from the admin site or MCP server, say) are
    serialised and the second sees the broadcast the first created rather
    than inserting another. Whatever was saved before a later step failed
    (the id of an inserted broadcast whose binding was rejected, or whose
    authorisation expired) is committed before the error is raised, so a
    broadcast is never orphaned.

    Returns what was done to the broadcast (``"created"``, ``"updated"`` or
    ``"removed"``), or ``None`` when there was nothing to do.
    """
    error = action = None
    with transaction.atomic():
        try:
            # The default manager annotates team titles through outer joins
            # that a row lock cannot be taken across.
            match = (
                Match._base_manager.select_related(
                    "stage__division__season__competition",
                )
                .select_for_update(of=("self",))
                .get(pk=match_pk)
            )
        except Match.DoesNotExist:
            # Match was deleted between enqueuing and execution; nothing to sync.
            logger.info("sync_live_stream skipped: match %s no longer exists", match_pk)
            return None
        try:
            action = _sync_live_stream(match, base_url)
        except (HttpError, RefreshError) as exc:
            error = exc
    if error is not None:
        raise error
    if action in ("created", "updated"):
        # Queued once the broadcast is committed, so a broker failure cannot
        # roll back the record of a broadcast YouTube has already accepted.
        set_youtube_thumbnail.s(match_pk).apply_async(countdown=10)
    return action


def _sync_live_stream(match, base_url):
    """Insert, update or delete the broadcast of a locked ``match``."""
    match_pk = match.pk
    season = match.stage.division.season

    if not (season.live_stream_client_id and season.live_stream_client_secret):
        return None

    if not match.live_stream and not match.external_identifier:
        return None  # Nothing to insert, update, or delete.

    if match.external_identifier and not match.live_stream:
        try:
            return _apply_sync(match, season, None)
        except HttpError as exc:
            logger.error("YouTube API error syncing match %s: %s", match_pk, exc)
            raise

    rejected = None
    tried = set()
    for short, label_only in _TITLE_FORMS:
        body = build_live_stream_body(
            match, base_url=base_url, short=short, label_only=label_only
        )
        if body is None:
            return None  # No scheduled time
        title = body["snippet"]["title"]
        if title in tried:
            # Nothing shorter in this form (no short titles are set, the
            # match has no label, or a custom template ignores the form), so
            # YouTube would only reject the same title again.
            continue
        tried.add(title)
        try:
            return _apply_sync(match, season, body)
        except HttpError as exc:
            if not _is_title_too_long(exc):
                logger.error("YouTube API error syncing match %s: %s", match_pk, exc)
                raise
            logger.warning(
                "YouTube rejected the title of match %s (%r), "
                "trying its next shorter form",
                match_pk,
                title,
            )
            rejected = exc
    logger.error("YouTube API error syncing match %s: %s", match_pk, rejected)
    raise rejected


def build_live_stream_event_body(event):
    """Build the YouTube broadcast body for an adhoc live stream event.

    Unlike matches, adhoc events carry their own author-supplied title and
    description, and an explicit scheduled start and stop time.
    """
    return {
        "snippet": {
            "title": event.title,
            "description": event.description,
            "scheduledStartTime": event.start.astimezone(ZoneInfo("UTC")).isoformat(),
            "scheduledEndTime": event.stop.astimezone(ZoneInfo("UTC")).isoformat(),
        },
        "status": {
            "privacyStatus": event.season.live_stream_privacy,
            "selfDeclaredMadeForKids": False,
        },
        "contentDetails": {
            "enableAutoStart": False,
            "enableAutoStop": False,
            "monitorStream": {
                "broadcastStreamDelayMs": 0,
                "enableMonitorStream": True,
            },
        },
    }


def _is_not_found(exc):
    """Return True when an HttpError indicates the resource no longer exists."""
    return getattr(getattr(exc, "resp", None), "status", None) == 404


def _apply_event_sync(event, season):
    """Apply a single update/delete + bind cycle against YouTube.

    The broadcast identifier is the event's primary key — the broadcast is
    created with the event, so there is no insert path here. A broadcast
    which has already been removed from the platform (404) is tolerated.

    Returns what was done to the broadcast: ``"updated"``, ``"removed"`` or
    ``"missing"`` when it no longer exists on the platform.
    """
    youtube = season.youtube

    if not event.live_stream:
        try:
            youtube.liveBroadcasts().delete(id=event.external_identifier).execute()
            logger.info("YouTube video %r deleted", event.external_identifier)
        except HttpError as exc:
            if not _is_not_found(exc):
                raise
            logger.info(
                "YouTube video %r already deleted", event.external_identifier
            )
        if event.live_stream_bind:
            event.live_stream_bind = None
            event.save(update_fields=["live_stream_bind"])
        return "removed"

    body = build_live_stream_event_body(event)
    body["id"] = event.external_identifier
    try:
        youtube.liveBroadcasts().update(
            part="snippet,status,contentDetails", body=body
        ).execute()
        logger.info("YouTube video %r updated", event.external_identifier)
    except HttpError as exc:
        if not _is_not_found(exc):
            raise
        # The broadcast was previously removed from the platform and cannot
        # be reinstated under the same identifier.
        logger.warning(
            "YouTube video %r no longer exists, skipping sync",
            event.external_identifier,
        )
        return "missing"

    stream_key = event.stream_key
    if stream_key is not None:
        bind = (
            youtube.liveBroadcasts()
            .bind(
                part="id,snippet,contentDetails,status",
                id=event.external_identifier,
                streamId=stream_key.external_identifier,
            )
            .execute()
        )
        bound = bind["contentDetails"].get("boundStreamId")
        if bound != event.live_stream_bind:
            event.live_stream_bind = bound
            event.save(update_fields=["live_stream_bind"])
    elif event.live_stream_bind:
        # The stream key has been unset since the broadcast was bound;
        # calling bind without a streamId removes the existing binding.
        youtube.liveBroadcasts().bind(
            part="id,snippet,contentDetails,status",
            id=event.external_identifier,
        ).execute()
        event.live_stream_bind = None
        event.save(update_fields=["live_stream_bind"])
    return "updated"


@shared_task
def sync_live_stream_event(event_pk):
    """Synchronize an adhoc live stream event with its YouTube broadcast.

    Updates or deletes the scheduled broadcast, pushes the thumbnail, and
    binds the broadcast to the selected stream key from the season's managed
    pool, as required by the current state of the event.

    The event row is locked for the duration so concurrent synchronisations
    are serialised, and whatever was saved before a rejection by YouTube is
    committed before the error is raised (see ``sync_live_stream``).

    Returns what was done to the broadcast (``"updated"``, ``"removed"`` or
    ``"missing"``), or ``None`` when there was nothing to do.
    """
    error = action = None
    with transaction.atomic():
        try:
            event = (
                LiveStreamEvent.objects.select_related(
                    "season__competition", "stream_key"
                )
                .select_for_update(of=("self",))
                .get(pk=event_pk)
            )
        except LiveStreamEvent.DoesNotExist:
            # Event was deleted between enqueuing and execution; nothing to sync.
            logger.info(
                "sync_live_stream_event skipped: event %s no longer exists", event_pk
            )
            return None
        season = event.season

        if not (season.live_stream_client_id and season.live_stream_client_secret):
            return None

        try:
            action = _apply_event_sync(event, season)
        except (HttpError, RefreshError) as exc:
            logger.error("YouTube API error syncing event %s: %s", event_pk, exc)
            error = exc
    if error is not None:
        raise error
    if action == "updated" and event.get_thumbnail_media_upload() is not None:
        # Queued once the update is committed (see ``sync_live_stream``).
        set_live_stream_event_thumbnail.s(event_pk).apply_async(countdown=10)
    return action


@shared_task
def set_live_stream_event_thumbnail(event_pk):
    """
    Asynchronously use the Google YouTube Data API to set the thumbnail for
    the adhoc live stream event specified.

    This function uses the database-stored thumbnail images via the
    MediaMemoryUpload class, with season fallback handled by the model.
    """
    obj = LiveStreamEvent.objects.get(pk=event_pk)

    media_body = obj.get_thumbnail_media_upload()

    if media_body is None:
        raise ValueError(f"No thumbnail available for live stream event {event_pk}")

    obj.season.youtube.thumbnails().set(
        videoId=obj.external_identifier,
        media_body=media_body,
    ).execute()


@shared_task
def delete_youtube_broadcast(season_pk, external_identifier):
    """Delete a YouTube broadcast that no longer has a local record.

    Used when an adhoc live stream event is deleted from the database while
    its broadcast is still scheduled on the YouTube platform.
    """
    try:
        season = Season.objects.get(pk=season_pk)
    except Season.DoesNotExist:
        logger.info(
            "delete_youtube_broadcast skipped: season %s no longer exists", season_pk
        )
        return

    if not (season.live_stream_client_id and season.live_stream_client_secret):
        return

    try:
        season.youtube.liveBroadcasts().delete(id=external_identifier).execute()
        logger.info("YouTube video %r deleted", external_identifier)
    except HttpError as exc:
        # The admin delete view destroys the broadcast before removing the
        # record, so this cleanup will usually find it already gone.
        if _is_not_found(exc):
            logger.info("YouTube video %r already deleted", external_identifier)
            return
        logger.error(
            "YouTube API error deleting broadcast %r: %s", external_identifier, exc
        )
        raise


@shared_task
def delete_youtube_stream(season_pk, external_identifier):
    """Delete a YouTube liveStream that no longer has a local record.

    Used when a managed stream key is deleted from the database while its
    liveStream resource still exists on the YouTube platform.
    """
    try:
        season = Season.objects.get(pk=season_pk)
    except Season.DoesNotExist:
        logger.info(
            "delete_youtube_stream skipped: season %s no longer exists", season_pk
        )
        return

    if not (season.live_stream_client_id and season.live_stream_client_secret):
        return

    try:
        season.youtube.liveStreams().delete(id=external_identifier).execute()
        logger.info("YouTube stream %r deleted", external_identifier)
    except HttpError as exc:
        # The admin delete view destroys the stream before removing the
        # record, so this cleanup will usually find it already gone.
        if _is_not_found(exc):
            logger.info("YouTube stream %r already deleted", external_identifier)
            return
        logger.error(
            "YouTube API error deleting stream %r: %s", external_identifier, exc
        )
        raise


def _is_transient_pdf_error(exc):
    """
    A timeout, a connection error or a 5xx from the PDF service is worth
    retrying; a 4xx or anything else will fail the same way again.
    """
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code >= 500
    return False


def _retry_transient_pdf_error(task, exc):
    if not _is_transient_pdf_error(exc):
        raise exc
    countdown = PDF_RENDER_RETRY_DELAY * 2**task.request.retries
    logger.warning("PDF service failed (%s), retrying in %ss.", exc, countdown)
    raise task.retry(exc=exc, countdown=countdown)


class PdfResultTask(Task):
    """
    A PDF render whose result the admin polls for, without the web process
    ever subscribing to it.

    Queueing a task whose result is kept makes Celery's Redis backend
    subscribe the web process to the task's result channel
    (``RedisBackend.on_task_call``), and the ``AsyncResult`` unsubscribes again
    when it is read or garbage collected. If that pub/sub connection has
    dropped, redis-py reconnects and re-subscribes while holding its own
    pub/sub lock, and the request hangs until gunicorn kills the worker.

    So the task is queued with ``ignore_result=True`` and stores its own
    result once it succeeds; failures, and the retries before a failure, are
    kept by ``store_errors_even_if_ignored``. The admin reads the state
    straight from the backend.
    """

    ignore_result = True
    store_errors_even_if_ignored = True

    def on_success(self, retval, task_id, args, kwargs):
        self.backend.store_result(task_id, retval, states.SUCCESS, request=self.request)


@shared_task(base=PdfResultTask, bind=True, max_retries=PDF_RENDER_MAX_RETRIES)
def generate_pdf_scorecards(
    self, match_pks, templates, extra_context, stage_pk=None, season_pk=None, **kwargs
):
    """
    Render scorecards for the given matches to PDF.

    Every argument must survive the configured task serializer (JSON by
    default), so callers pass primary keys rather than model instances. The
    ``competition``, ``season`` and ``stage`` model instances that the
    scorecard templates expect are loaded here and added to ``extra_context``.
    """
    matches = Match.objects.filter(pk__in=match_pks)
    extra_context = dict(extra_context or {})
    stage = None
    if stage_pk is not None:
        stage = Stage.objects.select_related("division__season__competition").get(
            pk=stage_pk
        )
        extra_context["stage"] = stage
        season = stage.division.season
    elif season_pk is not None:
        season = Season.objects.select_related("competition").get(pk=season_pk)
    else:
        season = None
    if season is not None:
        extra_context["season"] = season
        extra_context["competition"] = season.competition
    try:
        data = generate_scorecards(
            matches, templates, "pdf", extra_context, stage, **kwargs
        )
    except requests.RequestException as exc:
        _retry_transient_pdf_error(self, exc)
    # We can't JSON encode bytes, so we need to base64 encode the
    # PDF document before handing it back to the result backend.
    return base64.b64encode(data).decode("utf8")


@shared_task(base=PdfResultTask, bind=True, max_retries=PDF_RENDER_MAX_RETRIES)
def generate_pdf_grid(self, season, extra_context, date=None):
    dates = [date] if date is not None else None
    try:
        data: bytes = generate_fixture_grid(
            season,
            dates=dates,
            format="pdf",
            extra_context=extra_context,
            http_response=False,  # Get bytes back, not a response object
        )
    except requests.RequestException as exc:
        _retry_transient_pdf_error(self, exc)
    # We can't JSON encode bytes, so we need to base64 encode the
    # PDF document before handing it back to the result backend.
    return base64.b64encode(data).decode("utf8")


@shared_task
def set_youtube_thumbnail(match_pk):
    """
    Asynchronously use the Google YouTube Data API to set the thumbnail for
    the match specified.

    This function uses the database-stored thumbnail images via the
    MediaMemoryUpload class, with fallback logic handled by the model.
    """
    obj = Match.objects.get(pk=match_pk)
    season = obj.stage.division.season

    # Get thumbnail media upload (with built-in fallback logic)
    media_body = obj.get_thumbnail_media_upload()

    if media_body is None:
        raise ValueError(f"No thumbnail available for match {match_pk}")

    obj.stage.division.season.youtube.thumbnails().set(
        videoId=obj.external_identifier,
        media_body=media_body,
    ).execute()


@shared_task
def synchronise_mysideline_season(season_pk):
    """
    Converge a single season onto the competitions MySideline publishes for
    it. See :mod:`tournamentcontrol.competition.mysideline`.

    A remote failure raises so that the task is recorded as failed and the
    local data is left exactly as it was.
    """
    season = Season.objects.get(pk=season_pk)
    result = _mysideline_synchronise_season(season)
    return {
        "created": result.created,
        "updated": result.updated,
        "deleted": result.deleted,
        "detached": result.detached,
        "warnings": result.warnings,
    }


@shared_task
def synchronise_mysideline():
    """
    Synchronise every enabled, incomplete season that names a MySideline
    season within a competition that has a MySideline URL.

    Intended to be scheduled periodically (for example with Celery beat)
    by the deploying project; each season is isolated so that one failing
    remote fetch does not prevent the others from synchronising.
    """
    results = _mysideline_synchronise_all()
    return {pk: result.summary() for pk, result in results.items()}
