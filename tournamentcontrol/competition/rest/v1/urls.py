from django.conf.urls import include, url
from tournamentcontrol.competition.rest.v1._routers import *

urlpatterns = [
    url(r"^", router.urls),
    url(r"^", competition_router.urls),
    url(r"^", season_router.urls),
    url(r"^", division_router.urls),
]
