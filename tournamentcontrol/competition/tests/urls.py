from django.urls import include, path

from touchtechnology.common.sites import AccountsSite
from tournamentcontrol.competition.sites import calculator, competition

accounts = AccountsSite()

urlpatterns = [
    path("accounts/", accounts.urls),
    path("api/", include("touchtechnology.common.rest.urls")),
    path("tournament-planner/", calculator.urls),
    path("", competition.urls),
]
