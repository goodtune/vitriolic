from django.db import models
from tournamentcontrol.competition.query import LadderEntryQuerySet, MatchQuerySet, TeamQuerySet


class LadderEntryManager(models.Manager.from_queryset(LadderEntryQuerySet)):
    def get_queryset(self):
        return super(LadderEntryManager, self).get_queryset()._all()


class MatchManager(models.Manager.from_queryset(MatchQuerySet)):
    def get_queryset(self):
        return super(MatchManager, self).get_queryset()._rank_importance()


class TeamManager(models.Manager.from_queryset(TeamQuerySet)):
    def get_queryset(self):
        return super(TeamManager, self).get_queryset()._rank_division()
