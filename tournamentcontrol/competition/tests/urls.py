from django.conf.urls import url
from touchtechnology.common.sites import AccountsSite
from tournamentcontrol.competition.sites import competition

accounts = AccountsSite()

urlpatterns = [
    url(r'^accounts/', accounts.urls),
    url(r'^', competition.urls),
]
