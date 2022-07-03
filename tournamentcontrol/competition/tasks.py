import base64

from celery import shared_task

from tournamentcontrol.competition.models import Match, Stage
from tournamentcontrol.competition.utils import generate_scorecards


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
