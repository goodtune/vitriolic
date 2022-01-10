from django.urls import include, path

from touchtechnology.common.sites import AccountsSite
from tournamentcontrol.competition.sites import competition

accounts = AccountsSite()

urlpatterns = [
    path("accounts/", accounts.urls),
    path("api/", include("tournamentcontrol.competition.rest.urls")),
    path("", competition.urls),
]
