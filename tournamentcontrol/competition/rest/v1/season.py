from rest_framework import serializers
from rest_framework_nested.serializers import NestedHyperlinkedModelSerializer

from tournamentcontrol.competition import models

from .viewsets import SlugViewSet


class PlaceSerializer(serializers.ModelSerializer):
    timezone = serializers.SerializerMethodField()

    class Meta:
        model = models.Place
        fields = ("id", "title", "abbreviation", "timezone")

    def get_timezone(self, obj):
        tz = obj.timezone
        if tz is None:
            return None
        return getattr(tz, "key", str(tz))


class RefereeClubSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Club
        fields = ("title", "abbreviation")


class ListRefereeSerializer(serializers.ModelSerializer):
    uuid = serializers.ReadOnlyField(source="person.uuid")
    first_name = serializers.ReadOnlyField(source="person.first_name")
    last_name = serializers.ReadOnlyField(source="person.last_name")

    club = RefereeClubSerializer(read_only=True)

    class Meta:
        model = models.SeasonReferee
        fields = ("id", "uuid", "first_name", "last_name", "club")


class ListDivisionSerializer(NestedHyperlinkedModelSerializer):
    parent_lookup_kwargs = {
        "competition_slug": "season__competition__slug",
        "season_slug": "season__slug",
    }

    class Meta:
        model = models.Division
        fields = ("title", "slug", "url")
        extra_kwargs = {
            "url": {
                "lookup_field": "slug",
                "view_name": "v1:competition:division-detail",
            },
            "season": {"lookup_field": "slug"},
        }


class ListSeasonSerializer(NestedHyperlinkedModelSerializer):
    parent_lookup_kwargs = {"competition_slug": "competition__slug"}

    class Meta:
        model = models.Season
        fields = ("title", "slug", "url")
        extra_kwargs = {
            "url": {
                "lookup_field": "slug",
                "view_name": "v1:competition:season-detail",
            },
            "competition": {"lookup_field": "slug"},
        }


class SeasonSerializer(ListSeasonSerializer):
    divisions = ListDivisionSerializer(many=True, read_only=True)
    referees = ListRefereeSerializer(many=True, read_only=True)

    class Meta(ListSeasonSerializer.Meta):
        fields = ("title", "slug", "url", "divisions", "referees")


class SeasonViewSet(SlugViewSet):
    serializer_class = SeasonSerializer
    list_serializer_class = ListSeasonSerializer

    def get_queryset(self):
        return models.Season.objects.filter(
            competition__slug=self.kwargs["competition_slug"]
        )
