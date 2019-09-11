from rest_framework_nested.serializers import NestedHyperlinkedModelSerializer
from tournamentcontrol.competition import models

from .viewsets import SlugViewSet


class ListDivisionSerializer(NestedHyperlinkedModelSerializer):
    parent_lookup_kwargs = {
        "competition_slug": "season__competition__slug",
        "season_slug": "season__slug",
    }

    class Meta:
        model = models.Division
        fields = ("title", "slug", "url")
        extra_kwargs = {
            "url": {"lookup_field": "slug"},
            "division": {"lookup_field": "slug"},
        }


class ListSeasonSerializer(NestedHyperlinkedModelSerializer):
    parent_lookup_kwargs = {"competition_slug": "competition__slug"}

    class Meta:
        model = models.Season
        fields = ("title", "slug", "url")
        extra_kwargs = {
            "url": {"lookup_field": "slug"},
            "competition": {"lookup_field": "slug"},
        }


class SeasonSerializer(ListSeasonSerializer):
    divisions = ListDivisionSerializer(many=True, read_only=True)

    class Meta(ListSeasonSerializer.Meta):
        fields = ("title", "slug", "url", "divisions")


class SeasonViewSet(SlugViewSet):
    serializer_class = SeasonSerializer
    list_serializer_class = ListSeasonSerializer

    def get_queryset(self):
        return models.Season.objects.filter(
            competition__slug=self.kwargs["competition_slug"]
        )
