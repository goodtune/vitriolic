from rest_framework import viewsets
from tournamentcontrol.competition import models
from tournamentcontrol.competition.rest import serializers


class ClubViewSet(viewsets.ModelViewSet):
    queryset = models.Club.objects.all()
    serializer_class = serializers.ClubSerializer
    lookup_field = "slug"


class CompetitionViewSet(viewsets.ModelViewSet):
    queryset = models.Competition.objects.all()
    serializer_class = serializers.CompetitionSerializer
    lookup_field = "slug"


class SeasonViewSet(viewsets.ModelViewSet):
    serializer_class = serializers.SeasonSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return models.Season.objects.filter(
            competition__slug=self.kwargs["competition_slug"]
        )


class DivisionViewSet(viewsets.ModelViewSet):
    serializer_class = serializers.DivisionSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return models.Division.objects.filter(
            season__slug=self.kwargs["season_slug"],
            season__competition__slug=self.kwargs["competition_slug"],
        )


class TeamViewSet(viewsets.ModelViewSet):
    serializer_class = serializers.TeamSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return models.Team.objects.filter(
            division__slug=self.kwargs["division_slug"],
            division__season__slug=self.kwargs["season_slug"],
            division__season__competition__slug=self.kwargs["competition_slug"],
        )


class StageViewSet(viewsets.ModelViewSet):
    serializer_class = serializers.StageSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return models.Stage.objects.filter(
            division__slug=self.kwargs["division_slug"],
            division__season__slug=self.kwargs["season_slug"],
            division__season__competition__slug=self.kwargs["competition_slug"],
        )
