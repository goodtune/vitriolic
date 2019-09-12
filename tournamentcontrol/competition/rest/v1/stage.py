from rest_framework import serializers
from tournamentcontrol.competition import models

from .division import ListMatchSerializer, ListTeamSerializer
from .viewsets import SlugViewSet


class StageSerializer(serializers.ModelSerializer):
    matches = ListMatchSerializer(many=True, read_only=True)
    teams = ListTeamSerializer(many=True, read_only=True)

    class Meta:
        model = models.Stage
        fields = ("title", "slug", "teams", "matches")


class StageViewSet(SlugViewSet):
    serializer_class = StageSerializer

    def get_queryset(self):
        return models.Stage.objects.filter(
            division__slug=self.kwargs["division_slug"],
            division__season__slug=self.kwargs["season_slug"],
            division__season__competition__slug=self.kwargs["competition_slug"],
        )
