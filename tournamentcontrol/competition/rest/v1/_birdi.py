"""
LiveScore / LiveStream integration API resources.

This is not considered official API and should not be relied upon - it could change
at any time with changing needs.
"""

from dateutil.relativedelta import relativedelta
from rest_framework import serializers, viewsets
from tournamentcontrol.competition import models


class MatchSerializer(serializers.Serializer):

    id = serializers.UUIDField(source="uuid", read_only=True)
    scheduledStartTime = serializers.DateTimeField(source="datetime", read_only=True)
    scheduledEndTime = serializers.SerializerMethodField(read_only=True)
    comp = serializers.ReadOnlyField(source="stage.division.title")
    round = serializers.SerializerMethodField(read_only=True)
    teamA = serializers.SerializerMethodField(read_only=True)
    teamB = serializers.SerializerMethodField(read_only=True)
    location = serializers.CharField(source="play_at", read_only=True)

    def get_round(self, obj):
        return obj.label or str(obj.round)

    def _get_team(self, obj):
        if obj is None:
            return
        if obj.club is not None:
            return obj.club.abbreviation
        return obj.title

    def get_teamA(self, obj):
        return self._get_team(obj.home_team)

    def get_teamB(self, obj):
        return self._get_team(obj.away_team)

    def get_scheduledEndTime(self, obj):
        if obj.datetime is not None:
            return obj.datetime + relativedelta(minutes=50)


class MatchViewSet(viewsets.ModelViewSet):
    """
    This endpoint is used by the BIRDI developed application to seed it's
    list of matches for use with the YouTube Event API for live streams.
    """

    lookup_field = "uuid"
    serializer_class = MatchSerializer

    def get_queryset(self):
        return models.Match.objects.filter(
            stage__division__season__slug=self.kwargs["season_slug"],
            stage__division__season__competition__slug=self.kwargs["competition_slug"],
        )
