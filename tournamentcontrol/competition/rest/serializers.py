from rest_framework import serializers
from rest_framework_nested.relations import NestedHyperlinkedRelatedField
from rest_framework_nested.serializers import NestedHyperlinkedModelSerializer
from tournamentcontrol.competition import models


class ClubSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = models.Club
        fields = (
            "title",
            "slug",
            "abbreviation",
            "url",
            "facebook",
            "twitter",
            "youtube",
            "website",
        )
        extra_kwargs = {"url": {"lookup_field": "slug"}}


class StageSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Stage
        fields = ("title", "slug")


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Team
        fields = ("title", "slug", "club")


class DivisionSerializer(NestedHyperlinkedModelSerializer):
    parent_lookup_kwargs = {
        "season_slug": "season__slug",
        "competition_slug": "season__competition__slug",
    }

    season = NestedHyperlinkedRelatedField(
        read_only=True,
        view_name="season-detail",
        lookup_field="slug",
        parent_lookup_kwargs={"competition_slug": "competition__slug"},
    )

    teams = NestedHyperlinkedRelatedField(
        many=True,
        read_only=True,
        view_name="team-detail",
        lookup_field="slug",
        parent_lookup_kwargs={
            "competition_slug": "division__season__competition__slug",
            "season_slug": "division__season__slug",
            "division_slug": "division__slug",
        },
    )

    stages = NestedHyperlinkedRelatedField(
        many=True,
        read_only=True,
        view_name="stage-detail",
        lookup_field="slug",
        parent_lookup_kwargs={
            "competition_slug": "division__season__competition__slug",
            "season_slug": "division__season__slug",
            "division_slug": "division__slug",
        },
    )

    class Meta:
        model = models.Division
        fields = ("title", "slug", "teams", "stages", "url", "season")
        extra_kwargs = {
            "url": {"lookup_field": "slug"},
            "season": {"lookup_field": "slug"},
        }


class SeasonSerializer(NestedHyperlinkedModelSerializer):
    parent_lookup_kwargs = {"competition_slug": "competition__slug"}

    divisions = NestedHyperlinkedRelatedField(
        many=True,
        read_only=True,
        view_name="division-detail",
        lookup_field="slug",
        parent_lookup_kwargs={
            "competition_slug": "season__competition__slug",
            "season_slug": "season__slug",
        },
    )

    class Meta:
        model = models.Season
        fields = ("title", "slug", "url", "divisions", "competition")
        extra_kwargs = {
            "url": {"lookup_field": "slug"},
            "competition": {"lookup_field": "slug"},
        }


class CompetitionSerializer(serializers.HyperlinkedModelSerializer):
    seasons = NestedHyperlinkedRelatedField(
        many=True,
        read_only=True,
        view_name="season-detail",
        lookup_field="slug",
        parent_lookup_kwargs={"competition_slug": "competition__slug"},
    )

    class Meta:
        model = models.Competition
        fields = ("title", "slug", "url", "seasons")
        extra_kwargs = {"url": {"lookup_field": "slug"}}
