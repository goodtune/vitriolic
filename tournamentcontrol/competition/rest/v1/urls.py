from tournamentcontrol.competition.rest.v1._routers import (
    router,
    competition_router,
    season_router,
    division_router,
)

urlpatterns = (
    router.urls + competition_router.urls + season_router.urls + division_router.urls
)
