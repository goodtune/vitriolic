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
        if obj.club_id is not None:
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
        return (
            models.Match.objects.select_related(
                "stage__division__season__competition",
                "home_team__club",
                "away_team__club",
                "play_at",
            )
            .filter(
                stage__division__season__slug=self.kwargs["season_slug"],
                stage__division__season__competition__slug=self.kwargs[
                    "competition_slug"
                ],
            )
            .defer(
                # don't select text fields
                "stage__copy",
                "stage__division__copy",
                "stage__division__season__copy",
                "stage__division__season__competition__copy",
                # unused home team fields
                "home_team__club__short_title",
                "home_team__club__slug",
                "home_team__club__email",
                "home_team__club__website",
                "home_team__club__twitter",
                "home_team__club__facebook",
                "home_team__club__youtube",
                "home_team__club__primary",
                "home_team__club__primary_position",
                # unused away team fields
                "away_team__club__short_title",
                "away_team__club__slug",
                "away_team__club__email",
                "away_team__club__website",
                "away_team__club__twitter",
                "away_team__club__facebook",
                "away_team__club__youtube",
                "away_team__club__primary",
                "away_team__club__primary_position",
                # long textual fields that are unused
                "stage__division__points_formula",
                "play_at__latlng",
            )
        )
