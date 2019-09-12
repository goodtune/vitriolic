from django.conf.urls import include, url
from tournamentcontrol.competition.rest.v1._routers import *

urlpatterns = [
    url(r"^", include(router.urls)),
    url(r"^", include(competition_router.urls)),
    url(r"^", include(season_router.urls)),
    url(r"^", include(division_router.urls)),
]
