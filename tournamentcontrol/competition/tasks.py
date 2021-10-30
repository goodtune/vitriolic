from celery import shared_task

from tournamentcontrol.competition.utils import generate_scorecards


@shared_task
def generate_pdf_scorecards(
    match_pks, templates, extra_context, stage_pk=None, **kwargs
):
    matches = Match.objects.filter(pk__in=match_pks)
    stage = None
    if stage_pk is not None:
        stage = Stage.objects.get(pk=stage_pk)
    return generate_scorecards(
        matches, templates, "pdf", extra_context, stage, **kwargs
    )
