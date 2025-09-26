from rest_framework import serializers
from rest_framework_nested.serializers import NestedHyperlinkedModelSerializer

from tournamentcontrol.competition import models

from .club import ClubSerializer
from .season import PlaceSerializer
from .viewsets import SlugViewSet


class ListTeamSerializer(serializers.ModelSerializer):
    club = ClubSerializer(read_only=True)

    class Meta:
        model = models.Team
        fields = ("id", "title", "slug", "club")


class LadderSummarySerializer(serializers.ModelSerializer):
    team = serializers.SerializerMethodField(read_only=True)
    stage_group = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = models.LadderSummary
        fields = (
            "team",
            "stage_group",
            "played",
            "win",
            "loss",
            "draw",
            "bye",
            "forfeit_for",
            "forfeit_against",
            "score_for",
            "score_against",
            "difference",
            "percentage",
            "bonus_points",
            "points",
        )

    def get_team(self, obj):
        return obj.team.pk

    def get_stage_group(self, obj):
        return obj.stage_group.pk if obj.stage_group else None


class ListMatchSerializer(serializers.ModelSerializer):
    round = serializers.SerializerMethodField(read_only=True)
    home_team = serializers.SerializerMethodField(read_only=True)
    away_team = serializers.SerializerMethodField(read_only=True)
    stage_group = serializers.SerializerMethodField(read_only=True)
    play_at = PlaceSerializer(read_only=True)

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
            "stage_group",
            "referees",
            "videos",
            "play_at",
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

    def get_stage_group(self, obj):
        return obj.stage_group.pk if obj.stage_group else None


class ListStageSerializer(NestedHyperlinkedModelSerializer):
    parent_lookup_kwargs = {
        "competition_slug": "division__season__competition__slug",
        "season_slug": "division__season__slug",
        "division_slug": "division__slug",
    }

    matches = ListMatchSerializer(many=True, read_only=True)
    ladder_summary = LadderSummarySerializer(many=True, read_only=True)
    pools = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = models.Stage
        fields = ("title", "slug", "url", "matches", "ladder_summary", "pools")
        extra_kwargs = {
            "url": {"lookup_field": "slug", "view_name": "v1:competition:stage-detail"}
        }

    def get_pools(self, obj):
        return [{"id": pool.pk, "title": pool.title} for pool in obj.pools.all()]


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
                "stages__ladder_summary",
            )
        )
