from datetime import timedelta
from django.db import transaction
from tournamentcontrol.competition.models import (
    MatchEvent,
    MatchEventType,
    SimpleScoreMatchStatistic,
)


def record_score(match, period, seconds, team, scorer, assist=None, points=1):
    """
    Create a SCORE (+ optional ASSIST) event **and** update Match / Statistic
    aggregates so existing ladder code keeps working unchanged.
    """
    offset = timedelta(seconds=seconds)

    with transaction.atomic():
        MatchEvent.objects.create(
            match=match,
            period=period,
            offset=offset,
            type=MatchEventType.SCORE,
            team=team,
            player=scorer,
            payload={"points": points},
        )
        if assist:
            MatchEvent.objects.create(
                match=match,
                period=period,
                offset=offset,
                type=MatchEventType.ASSIST,
                team=team,
                player=assist,
                related_player=scorer,
            )
        # bump tallies used elsewhere
        stat, _ = SimpleScoreMatchStatistic.objects.get_or_create(
            match=match, player=scorer, defaults={"played": 1}
        )
        stat.points = (stat.points or 0) + points
        stat.save(update_fields=["points"])
