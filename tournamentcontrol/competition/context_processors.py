from tournamentcontrol.competition.models import Match


def in_progress(request):
    return {"in_progress_matches": Match.objects.in_progress()}
