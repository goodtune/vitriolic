"""
Signal receivers that turn result changes into ops events. Connected once
by ``OpsSite``; nothing is connected when the site is never constructed.
"""

from tournamentcontrol.competition.ops import events
from tournamentcontrol.competition.signals.custom import (
    score_updated,
    statistics_updated,
)


def describe(match):
    return "%s · %s v %s" % (
        match.stage.division.title,
        match.get_home_team_plain(),
        match.get_away_team_plain(),
    )


def score_summary(match):
    division = match.stage.division.title
    if match.is_bye:
        return "Bye · %s · %s" % (
            division,
            match.get_home_team_plain() or match.get_away_team_plain(),
        )
    if match.is_forfeit:
        winner = match.forfeit_winner.title if match.forfeit_winner else "double"
        return "Forfeit · %s · %s v %s → %s" % (
            division,
            match.get_home_team_plain(),
            match.get_away_team_plain(),
            winner,
        )
    return "Score · %s · %s %s–%s %s" % (
        division,
        match.get_home_team_plain(),
        match.home_team_score,
        match.away_team_score,
        match.get_away_team_plain(),
    )


def on_score_updated(sender, match, **kwargs):
    events.publish(
        match.stage.division.season_id,
        "bye-processed" if match.is_bye else "score-entered",
        actor=getattr(sender, "actor", None),
        summary=score_summary(match),
        match=match.pk,
        adjusted=bool(getattr(sender, "adjusted", False)),
    )


def on_statistics_updated(sender, match, **kwargs):
    events.publish(
        match.stage.division.season_id,
        "statistics-entered",
        actor=getattr(sender, "actor", None),
        summary="Scorers · " + describe(match),
        match=match.pk,
    )


def connect():
    score_updated.connect(on_score_updated, dispatch_uid="ops.score_updated")
    statistics_updated.connect(
        on_statistics_updated, dispatch_uid="ops.statistics_updated"
    )
