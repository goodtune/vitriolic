from celery import shared_task
from tournamentcontrol.competition.utils import generate_scorecards


@shared_task
def generate_pdf_scorecards(matches, templates, extra_context, stage=None,
                            **kwargs):
    return generate_scorecards(
        matches, templates, 'pdf', extra_context, stage, **kwargs)
