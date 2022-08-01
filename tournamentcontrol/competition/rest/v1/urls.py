from tournamentcontrol.competition.rest.v1._routers import (
    competition_router,
    division_router,
    router,
    season_router,
)

urlpatterns = (
    router.urls + competition_router.urls + season_router.urls + division_router.urls
)
