import base64

import requests
from celery import shared_task
from googleapiclient.http import MediaInMemoryUpload

from tournamentcontrol.competition.models import Match, Stage
from tournamentcontrol.competition.utils import (
    generate_fixture_grid,
    generate_scorecards,
)


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
