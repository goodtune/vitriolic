"""The public site with Tournament Ops mounted beside it, as a project would."""

from django.urls import path

from tournamentcontrol.competition.compops.sites import CompOpsSite
from tournamentcontrol.competition.tests.urls import urlpatterns as public

urlpatterns = [path("compops/", CompOpsSite().urls), *public]
