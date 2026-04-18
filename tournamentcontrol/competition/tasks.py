import base64
import logging
from zoneinfo import ZoneInfo

from celery import shared_task
from dateutil.relativedelta import relativedelta
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from googleapiclient.errors import HttpError

from tournamentcontrol.competition.models import Match, Stage
from tournamentcontrol.competition.utils import (
    generate_fixture_grid,
    generate_scorecards,
)

logger = logging.getLogger(__name__)


YOUTUBE_TITLE_MAX_LENGTH = 100


class _ShortTitle:
    """Wrap a SitemapNodeBase so ``str()`` returns ``short_title`` (or ``title``)."""

    def __init__(self, obj):
        self.__dict__["_obj"] = obj

    def __str__(self):
        if self._obj is None:
            return ""
        return self._obj.short_title or self._obj.title

    def __getattr__(self, name):
        return getattr(self._obj, name)


def build_live_stream_body(match, base_url=None, short=False):
    """Render title/description templates and build the YouTube broadcast body.

    Returns the body dict, or ``None`` if the match lacks a scheduled start time.

    When ``short`` is true, ``short_title`` is substituted for ``title`` on
    Competition/Season/Division/Stage in the rendered title and description.
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

    match_url = None
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
            match_url = None

    template_context = {
        "match": match,
        "competition": ctx_competition,
        "season": ctx_season,
        "division": ctx_division,
        "stage": ctx_stage,
        "match_url": match_url,
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

    stop_time = start_time + relativedelta(minutes=50)  # FIXME: hard coded

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


def _is_title_too_long(exc):
    """Return True when an HttpError indicates an exceeded title length."""
    content = getattr(exc, "content", b"") or b""
    if isinstance(content, (bytes, bytearray)):
        try:
            content = content.decode("utf-8", errors="replace")
        except Exception:
            content = ""
    needle = str(content).lower()
    if "title" not in needle:
        return False
    return any(
        marker in needle
        for marker in ("too long", "maxlength", "max length", "invalidvalue")
    )


def _get_ground(place):
    """Return the Ground subclass instance for ``place``, or ``None``."""
    if place is None:
        return None
    try:
        return place.ground
    except Exception:
        return None


def _apply_sync(match, season, body):
    """Apply a single insert/update/delete + bind cycle against YouTube."""
    if match.external_identifier:
        if not match.live_stream:
            video_id = match.external_identifier
            season.youtube.liveBroadcasts().delete(id=video_id).execute()
            videos = list(match.videos or [])
            link = f"https://youtu.be/{video_id}"
            if link in videos:
                videos.remove(link)
            match.external_identifier = None
            match.videos = videos or None
            match.save(update_fields=["external_identifier", "videos"])
            logger.info("YouTube video %r deleted", video_id)
            return

        body["id"] = match.external_identifier
        season.youtube.liveBroadcasts().update(
            part="snippet,status,contentDetails", body=body
        ).execute()
        logger.info("YouTube video %r updated", match.external_identifier)
        set_youtube_thumbnail.s(match.pk).apply_async(countdown=10)
    elif match.live_stream:
        broadcast = (
            season.youtube.liveBroadcasts()
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
        set_youtube_thumbnail.s(match.pk).apply_async(countdown=10)

    ground = _get_ground(match.play_at)
    if match.external_identifier and ground and ground.external_identifier:
        bind = (
            season.youtube.liveBroadcasts()
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


@shared_task
def sync_live_stream(match_pk, base_url=None):
    """Synchronize a match with its YouTube broadcast.

    Creates, updates, deletes, and binds the live broadcast as required by the
    current state of the match. On a YouTube API title-length error, retries
    once with shortened titles (using ``short_title`` on Division, Season,
    Competition, and Stage where set) so a recoverable failure remains
    non-fatal and the broadcast can still be created.
    """
    match = Match.objects.select_related(
        "stage__division__season__competition",
    ).get(pk=match_pk)
    season = match.stage.division.season

    if not (season.live_stream_client_id and season.live_stream_client_secret):
        return

    for short in (False, True):
        body = build_live_stream_body(match, base_url=base_url, short=short)
        if body is None:
            return  # No scheduled time
        try:
            _apply_sync(match, season, body)
            return
        except HttpError as exc:
            if not short and _is_title_too_long(exc):
                logger.warning(
                    "YouTube rejected match %s title length, retrying with short titles",
                    match_pk,
                )
                continue
            logger.error("YouTube API error syncing match %s: %s", match_pk, exc)
            raise


@shared_task
def generate_pdf_scorecards(
    match_pks, templates, extra_context, stage_pk=None, **kwargs
):
    matches = Match.objects.filter(pk__in=match_pks)
    stage = None
    if stage_pk is not None:
        stage = Stage.objects.get(pk=stage_pk)
    data = generate_scorecards(
        matches, templates, "pdf", extra_context, stage, **kwargs
    )
    # We can't JSON encode bytes, so we need to base64 encode the
    # PDF document before handing it back to the result backend.
    return base64.b64encode(data).decode("utf8")


@shared_task
def generate_pdf_grid(season, extra_context, date=None):
    dates = [date] if date is not None else None
    data: bytes = generate_fixture_grid(
        season,
        dates=dates,
        format="pdf",
        extra_context=extra_context,
        http_response=False,  # Get bytes back, not a response object
    )
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
