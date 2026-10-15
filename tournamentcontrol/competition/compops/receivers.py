"""
Signal receivers that turn result changes into ops events. Connected once
by ``CompOpsSite``; nothing is connected when the site is never constructed.
"""

from tournamentcontrol.competition.compops import events
from tournamentcontrol.competition.signals.custom import (
    score_updated,
    statistics_updated,
)


def describe(match):
    division = match.stage.division.title
    return f"{division} · {match.get_home_team_plain()} v {match.get_away_team_plain()}"


def score_summary(match):
    division = match.stage.division.title
    if match.is_bye:
        team = match.get_home_team_plain() or match.get_away_team_plain()
        return f"Bye · {division} · {team}"
    if match.is_forfeit:
        winner = match.forfeit_winner.title if match.forfeit_winner else "double"
        home, away = match.get_home_team_plain(), match.get_away_team_plain()
        return f"Forfeit · {division} · {home} v {away} → {winner}"
    home, away = match.get_home_team_plain(), match.get_away_team_plain()
    return f"Score · {division} · {home} {match.home_team_score}–{match.away_team_score} {away}"


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
    # Each side's formset sends the signal. The ops site saves the away side
    # last, so announce on that one, once both sides are in the database.
    if getattr(sender, "prefix", None) != "away":
        return
    events.publish(
        match.stage.division.season_id,
        "statistics-entered",
        actor=getattr(sender, "actor", None),
        summary="Scorers · " + describe(match),
        match=match.pk,
    )


def connect():
    score_updated.connect(on_score_updated, dispatch_uid="compops.score_updated")
    statistics_updated.connect(
        on_statistics_updated, dispatch_uid="compops.statistics_updated"
    )
