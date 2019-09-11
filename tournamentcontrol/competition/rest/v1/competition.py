from rest_framework import serializers
from rest_framework_nested.serializers import NestedHyperlinkedModelSerializer
from tournamentcontrol.competition import models

from .viewsets import SlugViewSet


class ListSeasonSerializer(NestedHyperlinkedModelSerializer):
    parent_lookup_kwargs = {"competition_slug": "competition__slug"}

    class Meta:
        model = models.Season
        fields = ("title", "slug", "url")
        extra_kwargs = {"url": {"lookup_field": "slug"}}


class ListCompetitionSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = models.Competition
        fields = ("title", "slug", "url")
        extra_kwargs = {"url": {"lookup_field": "slug"}}


class CompetitionSerializer(ListCompetitionSerializer):
    seasons = ListSeasonSerializer(many=True, read_only=True)

    class Meta(ListCompetitionSerializer.Meta):
        fields = ("title", "slug", "url", "seasons")


class CompetitionViewSet(SlugViewSet):
    queryset = models.Competition.objects.all()
    serializer_class = CompetitionSerializer
    list_serializer_class = ListCompetitionSerializer
