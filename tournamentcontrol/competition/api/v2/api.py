from typing import List
from uuid import UUID
from ninja import NinjaAPI, Router
from django.shortcuts import get_object_or_404
from tournamentcontrol.competition.models import Competition, Season, Division, Team, Match
from .schemas import CompetitionSchema, SeasonSchema, DivisionSchema, TeamSchema, MatchSchema

api = NinjaAPI(title="Tournament Control API", version="2.0.0")

# Create routers
competition_router = Router()
season_router = Router()
division_router = Router()
team_router = Router()
match_router = Router()


@competition_router.get("/", response=List[CompetitionSchema])
def list_competitions(request):
    """List all competitions"""
    return Competition.objects.all()


@competition_router.get("/{slug}", response=CompetitionSchema)
def get_competition(request, slug: str):
    """Get a specific competition by slug"""
    return get_object_or_404(Competition, slug=slug)


@season_router.get("/{competition}/{season}", response=SeasonSchema)
def get_season(request, competition: str, season: str):
    """Get a specific season by slug"""
    return get_object_or_404(
        Season,
        slug=season,
        competition__slug=competition
    )


@division_router.get("/{competition}/{season}/{division}", response=DivisionSchema)
def get_division(request, competition: str, season: str, division: str):
    """Get a specific division by slug"""
    return get_object_or_404(
        Division,
        slug=division,
        season__slug=season,
        season__competition__slug=competition
    )


@division_router.get("/{competition}/{season}/{division}/team", response=List[TeamSchema])
def list_teams(request, competition: str, season: str, division: str):
    """List all teams in a division"""
    division_obj = get_object_or_404(
        Division,
        slug=division,
        season__slug=season,
        season__competition__slug=competition
    )
    return division_obj.teams.all()


@team_router.get("/{competition}/{season}/{division}/team/{team}", response=TeamSchema)
def get_team(request, competition: str, season: str, division: str, team: str):
    """Get a specific team by slug"""
    return get_object_or_404(
        Team,
        slug=team,
        division__slug=division,
        division__season__slug=season,
        division__season__competition__slug=competition
    )


@match_router.get("/{competition}/match", response=List[MatchSchema])
def list_competition_matches(request, competition: str):
    """List all matches in a competition"""
    return Match.objects.filter(
        stage__division__season__competition__slug=competition
    )


@match_router.get("/{competition}/match/{uuid}", response=MatchSchema)
def get_competition_match(request, competition: str, uuid: UUID):
    """Get a specific match by UUID in a competition"""
    return get_object_or_404(
        Match,
        uuid=uuid,
        stage__division__season__competition__slug=competition
    )


@match_router.get("/{competition}/{season}/match", response=List[MatchSchema])
def list_season_matches(request, competition: str, season: str):
    """List all matches in a season"""
    return Match.objects.filter(
        stage__division__season__slug=season,
        stage__division__season__competition__slug=competition
    )


@match_router.get("/{competition}/{season}/match/{uuid}", response=MatchSchema)
def get_season_match(request, competition: str, season: str, uuid: UUID):
    """Get a specific match by UUID in a season"""
    return get_object_or_404(
        Match,
        uuid=uuid,
        stage__division__season__slug=season,
        stage__division__season__competition__slug=competition
    )


@match_router.get("/{competition}/{season}/{division}/match", response=List[MatchSchema])
def list_division_matches(request, competition: str, season: str, division: str):
    """List all matches in a division"""
    return Match.objects.filter(
        stage__division__slug=division,
        stage__division__season__slug=season,
        stage__division__season__competition__slug=competition
    )


@match_router.get("/{competition}/{season}/{division}/match/{uuid}", response=MatchSchema)
def get_division_match(request, competition: str, season: str, division: str, uuid: UUID):
    """Get a specific match by UUID in a division"""
    return get_object_or_404(
        Match,
        uuid=uuid,
        stage__division__slug=division,
        stage__division__season__slug=season,
        stage__division__season__competition__slug=competition
    )


@match_router.get("/{competition}/{season}/{division}/team/{team}/match", response=List[MatchSchema])
def list_team_matches(request, competition: str, season: str, division: str, team: str):
    """List all matches for a team"""
    team_obj = get_object_or_404(
        Team,
        slug=team,
        division__slug=division,
        division__season__slug=season,
        division__season__competition__slug=competition
    )
    # Get matches where team is either home or away
    return Match.objects.filter(
        stage__division__slug=division,
        stage__division__season__slug=season,
        stage__division__season__competition__slug=competition
    ).filter(
        home_team=team_obj
    ) | Match.objects.filter(
        stage__division__slug=division,
        stage__division__season__slug=season,
        stage__division__season__competition__slug=competition,
        away_team=team_obj
    )


@match_router.get("/{competition}/{season}/{division}/team/{team}/match/{uuid}", response=MatchSchema)
def get_team_match(request, competition: str, season: str, division: str, team: str, uuid: UUID):
    """Get a specific match by UUID for a team"""
    team_obj = get_object_or_404(
        Team,
        slug=team,
        division__slug=division,
        division__season__slug=season,
        division__season__competition__slug=competition
    )
    # Get a specific match where team is either home or away
    return get_object_or_404(
        Match,
        uuid=uuid,
        stage__division__slug=division,
        stage__division__season__slug=season,
        stage__division__season__competition__slug=competition,
    ).filter(
        home_team=team_obj
    ) | Match.objects.filter(
        uuid=uuid,
        stage__division__slug=division,
        stage__division__season__slug=season,
        stage__division__season__competition__slug=competition,
        away_team=team_obj
    )


# Register routers
api.add_router("/competition", competition_router)
api.add_router("/competition", season_router)
api.add_router("/competition", division_router)
api.add_router("/competition", team_router)
api.add_router("/competition", match_router)
