from django.conf.urls import include, url

from touchtechnology.common.sites import AccountsSite
from tournamentcontrol.competition.sites import competition

accounts = AccountsSite()

urlpatterns = [
    url(r'^accounts/', include(accounts.urls)),
    url(r'^', include(competition.urls)),
]
