from rest_framework import serializers

from tournamentcontrol.competition import models

from .division import ListMatchSerializer, ListTeamSerializer
from .viewsets import SlugViewSet


class StageSerializer(serializers.ModelSerializer):
    matches = ListMatchSerializer(many=True, read_only=True)
    teams = ListTeamSerializer(many=True, read_only=True)
    pools = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = models.Stage
        fields = ("title", "slug", "teams", "matches", "pools")

    def get_pools(self, obj):
        return [{"id": pool.pk, "title": pool.title} for pool in obj.pools.all()]


class StageViewSet(SlugViewSet):
    serializer_class = StageSerializer

    def get_queryset(self):
        return models.Stage.objects.filter(
            division__slug=self.kwargs["division_slug"],
            division__season__slug=self.kwargs["season_slug"],
            division__season__competition__slug=self.kwargs["competition_slug"],
        )
