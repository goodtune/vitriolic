from rest_framework.routers import APIRootView, DefaultRouter
from rest_framework_nested import routers

from tournamentcontrol.competition.rest.v1 import *
from tournamentcontrol.competition.rest.v1 import _247, _birdi


class TournamentControl(APIRootView):
    """
    REST API for *Tournament Control*.
    """


class Router(DefaultRouter):
    APIRootView = TournamentControl


router = Router()
router.register(r"clubs", club.ClubViewSet)
router.register(r"competitions", competition.CompetitionViewSet)

competition_router = routers.NestedDefaultRouter(
    router, r"competitions", lookup="competition"
)
competition_router.register(r"seasons", season.SeasonViewSet, basename="season")

season_router = routers.NestedDefaultRouter(
    competition_router, r"seasons", lookup="season"
)
season_router.register(r"divisions", division.DivisionViewSet, basename="division")
season_router.register(r"players", _247.PersonViewSet, basename="players")
season_router.register(r"matches", _birdi.MatchViewSet, basename="match")

division_router = routers.NestedDefaultRouter(
    season_router, r"divisions", lookup="division"
)
division_router.register(r"stages", stage.StageViewSet, basename="stage")
