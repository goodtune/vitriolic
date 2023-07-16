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
    """
    obj = Match.objects.get(pk=match_pk)
    season = obj.stage.division.season

    img = requests.get(obj.live_stream_thumbnail or season.live_stream_thumbnail)
    img.raise_for_status()

    media_body = MediaInMemoryUpload(
        img.content,
        mimetype=img.headers["Content-Type"],
        resumable=True,
    )

    obj.stage.division.season.youtube.thumbnails().set(
        videoId=obj.external_identifier,
        media_body=media_body,
    ).execute()
