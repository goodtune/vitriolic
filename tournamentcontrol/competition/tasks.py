from celery import shared_task

from tournamentcontrol.competition import sportingpulse
from tournamentcontrol.competition.decorators import competition_by_slug
from tournamentcontrol.competition.utils import generate_scorecards


@shared_task
def generate_pdf_scorecards(matches, templates, extra_context, stage=None,
                            **kwargs):
    return generate_scorecards(
        matches, templates, 'pdf', extra_context, stage, **kwargs)


@shared_task
@competition_by_slug
def synchronise_with_sportingpulse(season=None, **kwargs):
    for division in season.divisions.filter(sportingpulse_url__isnull=False):
        sportingpulse.sync(division)
        # Issue with ladders, so force all matches to be re-saved and force a
        # ladder recalculation.
        for match in division.matches.all():
            match.save()
