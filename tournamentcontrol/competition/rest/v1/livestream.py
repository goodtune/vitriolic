"""
Live streaming REST API for Tournament Control.

This module provides REST API endpoints for managing live streams of matches.
"""

import warnings

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from tournamentcontrol.competition import models
from tournamentcontrol.competition.exceptions import (
    LiveStreamError,
    LiveStreamTransitionWarning,
)


class LiveStreamPagination(PageNumberPagination):
    """Pagination class for livestream matches."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class MinimalCompetitionSerializer(serializers.ModelSerializer):
    """Minimal competition details for nested serialization."""

    class Meta:
        model = models.Competition
        fields = ("id", "title", "slug")


class MinimalSeasonSerializer(serializers.ModelSerializer):
    """Minimal season details for nested serialization."""

    class Meta:
        model = models.Season
        fields = ("id", "title", "slug")


class MinimalDivisionSerializer(serializers.ModelSerializer):
    """Minimal division details for nested serialization."""

    class Meta:
        model = models.Division
        fields = ("id", "title", "slug")


class MinimalStageSerializer(serializers.ModelSerializer):
    """Minimal stage details for nested serialization."""

    class Meta:
        model = models.Stage
        fields = ("id", "title", "slug")


class MinimalClubSerializer(serializers.ModelSerializer):
    """Minimal club details for nested serialization."""

    class Meta:
        model = models.Club
        fields = ("id", "title", "slug")


class MinimalTeamSerializer(serializers.ModelSerializer):
    """Minimal team details for nested serialization."""

    club = MinimalClubSerializer(read_only=True)

    class Meta:
        model = models.Team
        fields = ("id", "title", "slug", "club")


class LiveStreamMatchSerializer(serializers.HyperlinkedModelSerializer):
    """
    Serializer for matches with live streaming capabilities.

    Uses minimal nested data and provides URLs for full details.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="v1:competition:livestream-detail",
        lookup_field="uuid",
    )
    stage = MinimalStageSerializer(read_only=True)
    division = MinimalDivisionSerializer(source="stage.division", read_only=True)
    season = MinimalSeasonSerializer(source="stage.division.season", read_only=True)
    competition = MinimalCompetitionSerializer(
        source="stage.division.season.competition", read_only=True
    )
    home_team = serializers.SerializerMethodField()
    away_team = serializers.SerializerMethodField()
    venue = serializers.SerializerMethodField()
    round = serializers.SerializerMethodField()

    class Meta:
        model = models.Match
        fields = (
            "id",
            "uuid",
            "url",
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
            "stage",
            "division",
            "season",
            "competition",
            "venue",
            "external_identifier",
            "live_stream",
            "live_stream_bind",
            "live_stream_thumbnail",
        )

    def get_round(self, obj):
        """Get round number or label."""
        return obj.label or f"Round {obj.round}"

    def get_venue(self, obj):
        """Get minimal venue information."""
        if obj.play_at:
            return {
                "id": obj.play_at.id,
                "title": obj.play_at.title,
                "abbreviation": obj.play_at.abbreviation,
            }
        return None

    def _get_team(self, obj, home_or_away):
        """Get team data, handling undecided teams."""
        team = getattr(obj, f"get_{home_or_away}_team_plain")()
        if isinstance(team, (models.Team, models.ByeTeam)):
            if hasattr(team, "pk"):
                # Return minimal team data for decided teams
                return MinimalTeamSerializer(team, context=self.context).data
            else:
                # Handle ByeTeam
                return {"id": None, "title": str(team), "slug": None, "club": None}
        # Return string representation for undecided teams
        return {"id": None, "title": str(team), "slug": None, "club": None}

    def get_home_team(self, obj):
        """Get home team data."""
        return self._get_team(obj, "home")

    def get_away_team(self, obj):
        """Get away team data."""
        return self._get_team(obj, "away")


class LiveStreamTransitionSerializer(serializers.Serializer):
    """Serializer for live stream status transitions."""

    status = serializers.ChoiceField(
        choices=[
            ("testing", "Testing"),
            ("live", "Live"),
            ("complete", "Complete"),
        ],
        help_text="The target broadcast status",
    )


class LiveStreamMatchFilter(django_filters.FilterSet):
    """
    FilterSet for livestream matches with proper date validation.
    """

    date__gte = django_filters.DateFilter(
        field_name="date",
        lookup_expr="gte",
        help_text="Filter matches from this date onwards (YYYY-MM-DD format)",
    )
    date__lte = django_filters.DateFilter(
        field_name="date",
        lookup_expr="lte",
        help_text="Filter matches up to this date (YYYY-MM-DD format)",
    )
    season_id = django_filters.NumberFilter(
        field_name="stage__division__season_id", help_text="Filter by season ID"
    )

    class Meta:
        model = models.Match
        fields = ["date__gte", "date__lte", "season_id"]


class LiveStreamViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for live streaming matches.

    Provides paginated endpoints to list matches with live streaming capabilities,
    with optional filtering by date range and season.

    Also provides an endpoint to transition live stream status.
    """

    serializer_class = LiveStreamMatchSerializer
    lookup_field = "uuid"
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = LiveStreamMatchFilter
    pagination_class = LiveStreamPagination

    def get_queryset(self):
        """
        Get queryset of matches with live streaming capability.

        Returns matches that have an external_identifier (live stream ID).
        Additional filtering is handled by the FilterSet.
        """
        return (
            models.Match.objects.select_related(
                "stage__division__season__competition",
                "home_team__club",
                "away_team__club",
                "play_at",
            )
            .filter(
                # Only matches with live stream identifiers
                external_identifier__isnull=False
            )
            .exclude(external_identifier="")
            .order_by("date", "time", "datetime")
        )

    def check_permissions(self, request):
        """
        Check that the user has permission to access live streaming features.

        Requires 'change_match' permission, not necessarily superuser.
        """
        super().check_permissions(request)

        # Check for change_match permission
        if not request.user.has_perm("competition.change_match"):
            self.permission_denied(
                request,
                message="You do not have permission to access live streaming features.",
            )



    @action(
        detail=True, methods=["post"], serializer_class=LiveStreamTransitionSerializer
    )
    def transition(self, request, uuid=None):
        """
        Transition the live stream status of a specific match.

        POST data should include:
        - status: 'testing', 'live', or 'complete'
        """
        match = self.get_object()
        serializer = LiveStreamTransitionSerializer(data=request.data)

        if serializer.is_valid():
            status_value = serializer.validated_data["status"]

            try:
                # Use the Match model's transition method
                with warnings.catch_warnings(record=True) as w:
                    warnings.simplefilter("always")

                    response = match.transition_live_stream(status_value)

                    result = {
                        "success": True,
                        "message": f"Successfully transitioned to {status_value}",
                        "youtube_response": response,
                        "warnings": [],
                    }

                    # Include any warnings in the response
                    for warning in w:
                        if issubclass(warning.category, LiveStreamTransitionWarning):
                            result["warnings"].append(str(warning.message))

                    return Response(result)

            except LiveStreamError as exc:
                return Response(
                    {"success": False, "error": str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as exc:
                return Response(
                    {"success": False, "error": f"Unexpected error: {exc}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
