from datetime import timedelta

from dateutil.parser import parse
from dateutil.rrule import DAILY, WEEKLY
from django import template
from django.apps import apps
from django.db.models import Case, F, Q, Sum, When
from django.template.loader import get_template
from django.utils import timezone
from first import first

try:
    from itertools import zip_longest
except ImportError:
    from itertools import izip_longest as zip_longest

register = template.Library()


@register.filter
def get_competitions(node):
    return node.get_children().filter(content_type__model="competition")


@register.filter
def opponent(match, team):
    if not match:
        return None
    elif match.home_team == team:
        return match.get_away_team()
    elif match.away_team == team:
        return match.get_home_team()
    else:
        return None


@register.inclusion_tag(
    "tournamentcontrol/competition/next_date.html", takes_context=True
)
def next_date(context, season, offset=0, datestr=None):
    from tournamentcontrol.competition.models import Match, Season

    if isinstance(season, str):
        season = Season.objects.get(pk=season)

    # TODO make the offset a value stored on the competition
    if datestr is None:
        now = timezone.now() - timedelta(minutes=offset)
    else:
        now = parse(datestr) - timedelta(minutes=offset)

    # drop any signifigance less than the minute
    now = now.replace(second=0, microsecond=0)

    # start with just matches for this season (and by definition competition)
    matches = Match.objects.filter(
        stage__division__draft=False, stage__division__season=season
    ).select_related(
        "play_at",
        "home_team__club",
        "away_team__club",
        "home_team__division__season__competition",
        "away_team__division__season__competition",
        "stage__division__season__competition",
    )

    # restrict to matches starting after "now"
    later_today = Q(date__exact=now.date(), time__gte=now.time())
    tomorrow_onwards = Q(date__gt=now.date())
    matches = matches.filter(later_today | tomorrow_onwards)

    try:
        next_game_date = first(matches.dates("date", "day").order_by("date"))
    except Match.DoesNotExist:
        matches = matches.none()
        next_game_date = None
    else:
        matches = matches.filter(date=next_game_date).exclude(is_bye=True)

    next_round = None

    if season.mode == DAILY:
        # For tournaments we want to update the upcoming matches every timeslot
        try:
            next_round = matches.filter(
                home_team_score__isnull=True, away_team_score__isnull=True
            )[0]
        except IndexError:
            matches = matches.none()
        else:
            matches = matches.filter(date=next_round.date, time=next_round.time)

    elif season.mode == WEEKLY:
        # For a weekly competition we want to update the upcoming matches each
        # week and sorted by division.
        matches = matches.order_by("stage__division", *Match._meta.ordering)

    context.update(
        {
            "matches": matches,
            "next_game_date": next_game_date,
            "next_round": next_round,
            "competition": season.competition,
            "season": season,
        }
    )

    return context


@register.simple_tag(takes_context=True)
def ladder(context, stage):
    if stage.pools.count():
        ordering = stage.ladder_summary.model._meta.ordering
        summary = stage.ladder_summary.order_by("stage_group", *ordering)
        template_name = "tournamentcontrol/competition/ladder/pool.html"
    else:
        summary = stage.ladder_summary.all()
        template_name = "tournamentcontrol/competition/ladder/standard.html"

    context.update(
        {"summary": summary,}
    )

    tpl = get_template(template_name)
    return tpl.render(context)


@register.simple_tag
def score(match, team, template_name="tournamentcontrol/competition/_score.html"):
    """
    Output a score relative to the specified team. Also includes the 'status'
    of the result from the perspective of the team.

        ie. Win 6-4
            Lose 3-5
            Forfeit 0-6

    Use the third argument to specify an alternative template file name.
    """
    if team == match.home_team:
        team_score = match.home_team_score
        opponent_score = match.away_team_score
    else:
        team_score = match.away_team_score
        opponent_score = match.home_team_score

    if team_score is not None and opponent_score is not None:
        if team_score > opponent_score or team == match.forfeit_winner:
            result = "won"
        elif team_score < opponent_score or match.is_forfeit:
            result = "lost"
        elif team_score == opponent_score:
            result = "drew"
        else:
            raise ValueError(
                "An error has occured while determining the " "match result."
            )
    else:
        result = None

    context = {
        "result": result,
        "team_score": team_score,
        "opponent_score": opponent_score,
        "forfeit": match.is_forfeit,
    }

    t = template.loader.get_template(template_name)

    return t.render(context)


@register.filter
def teams_in_season(team_queryset, season):
    assert isinstance(season, apps.get_model("competition", "season"))
    return team_queryset.filter(division__season=season)


@register.filter
def teams_in_division(team_queryset, division):
    assert isinstance(division, apps.get_model("competition", "division"))
    return team_queryset.filter(division=division)


@register.filter
def players(team, pad_to=None):
    try:
        players = list(team.people.filter(is_player=True))
    except AttributeError:
        players = []
    if pad_to is not None:
        while len(players) < pad_to:
            players.append(None)
    return players


@register.filter
def pair(i1, i2):
    return list(zip_longest(i1, i2))


@register.inclusion_tag("tournamentcontrol/competition/templatetags/statistics.html")
def statistics(match):
    stats = match.statistics.filter(played__gt=0).select_related("player")

    home_stats = stats.filter(
        match__home_team__people__team=match.home_team,
        player__teamassociation__team=match.home_team,
    ).distinct()

    away_stats = stats.filter(
        match__away_team__people__team=match.away_team,
        player__teamassociation__team=match.away_team,
    ).distinct()

    context = {
        "match": match,
        "lines": list(zip_longest(home_stats, away_stats)),
        "home_stats": home_stats,
        "away_stats": away_stats,
    }

    return context


@register.inclusion_tag("tournamentcontrol/competition/templatetags/preview.html")
def preview(match):
    annotate = {
        "played": Sum(
            Case(
                When(
                    person__statistics__match__stage__division=match.stage.division,
                    then=F("person__statistics__played"),
                ),
                default=0,
            )
        ),
        "points": Sum(
            Case(
                When(
                    person__statistics__match__stage__division=match.stage.division,
                    then=F("person__statistics__points"),
                ),
                default=0,
            )
        ),
    }

    home_team = match.home_team.people.filter(is_player=True).annotate(**annotate)
    away_team = match.away_team.people.filter(is_player=True).annotate(**annotate)

    context = {
        "match": match,
        "lines": list(zip_longest(home_team, away_team)),
        "home_team": home_team,
        "away_team": away_team,
    }

    return context
