from django.db import models

from tournamentcontrol.competition.query import (
    LadderEntryQuerySet,
    MatchQuerySet,
)


class LadderEntryManager(models.Manager.from_queryset(LadderEntryQuerySet)):
    def get_queryset(self):
        return super().get_queryset()._all()


class MatchManager(models.Manager.from_queryset(MatchQuerySet)):
    def get_queryset(self):
        return super().get_queryset()._team_titles()
