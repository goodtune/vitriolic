from django.conf.urls import include, url
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from tournamentcontrol.competition.rest import views

router = DefaultRouter()
router.register(r"clubs", views.ClubViewSet)
router.register(r"competitions", views.CompetitionViewSet)

competition_router = routers.NestedDefaultRouter(
    router, r"competitions", lookup="competition"
)
competition_router.register(r"seasons", views.SeasonViewSet, base_name="season")

season_router = routers.NestedDefaultRouter(
    competition_router, r"seasons", lookup="season"
)
season_router.register(r"divisions", views.DivisionViewSet, base_name="division")

division_router = routers.NestedDefaultRouter(
    season_router, r"divisions", lookup="division"
)
division_router.register(r"teams", views.TeamViewSet, base_name="team")
division_router.register(r"stages", views.StageViewSet, base_name="stage")

urlpatterns = [
    url(r"^", include(router.urls)),
    url(r"^", include(competition_router.urls)),
    url(r"^", include(season_router.urls)),
    url(r"^", include(division_router.urls)),
    url(r"^api-auth/", include("rest_framework.urls")),
]
