from rest_framework import serializers
from rest_framework_nested.serializers import NestedHyperlinkedModelSerializer
from tournamentcontrol.competition import models

from .club import ClubSerializer
from .viewsets import SlugViewSet


class ListMatchSerializer(serializers.ModelSerializer):
    round = serializers.SerializerMethodField(read_only=True)
    home_team = serializers.SerializerMethodField(read_only=True)
    away_team = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = models.Match
        fields = (
            "id",
            "uuid",
            "round",
            "date",
            "time",
            "datetime",
            "is_bye",
            "is_washout",
            "home_team",
            "home_team_score",
            "away_team",
            "away_team_score",
            "referees",
            "videos",
        )

    def get_round(self, obj):
        return obj.label or "Round {}".format(obj.round)

    def _get_team(self, obj, home_or_away):
        team = getattr(obj, f"get_{home_or_away}_team_plain")()
        if isinstance(team, (models.Team, models.ByeTeam)):
            return team.pk
        return team

    def get_home_team(self, obj):
        return self._get_team(obj, "home")

    def get_away_team(self, obj):
        return self._get_team(obj, "away")


class ListStageSerializer(NestedHyperlinkedModelSerializer):
    parent_lookup_kwargs = {
        "competition_slug": "division__season__competition__slug",
        "season_slug": "division__season__slug",
        "division_slug": "division__slug",
    }

    matches = ListMatchSerializer(many=True, read_only=True)

    class Meta:
        model = models.Stage
        fields = ("title", "slug", "url", "matches")
        extra_kwargs = {"url": {"lookup_field": "slug"}}


class ListTeamSerializer(serializers.ModelSerializer):

    club = ClubSerializer(read_only=True)

    class Meta:
        model = models.Team
        fields = ("id", "title", "slug", "club")


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
            "season": {"lookup_field": "slug"},
        }


class DivisionSerializer(ListDivisionSerializer):
    teams = ListTeamSerializer(many=True, read_only=True)
    stages = ListStageSerializer(many=True, read_only=True)

    class Meta(ListDivisionSerializer.Meta):
        fields = ("title", "slug", "url", "teams", "stages")


class DivisionViewSet(SlugViewSet):
    serializer_class = DivisionSerializer
    list_serializer_class = ListDivisionSerializer

    def get_queryset(self):
        return (
            models.Division.objects.filter(
                season__slug=self.kwargs["season_slug"],
                season__competition__slug=self.kwargs["competition_slug"],
            )
            .select_related("season__competition")
            .prefetch_related(
                "teams__club",
                "stages__matches__home_team",
                "stages__matches__away_team",
            )
        )
