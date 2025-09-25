"""
Live streaming REST API for Tournament Control.

This module provides REST API endpoints for managing live streams of matches.
"""

import warnings
from datetime import datetime

import django_filters
from django.db.models import Q
from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from tournamentcontrol.competition import models
from tournamentcontrol.competition.exceptions import (
    LiveStreamError,
    LiveStreamTransitionWarning,
)
from tournamentcontrol.competition.rest.v1.club import ClubSerializer
from tournamentcontrol.competition.rest.v1.season import PlaceSerializer
from tournamentcontrol.competition.sites import permissions_required


class CompetitionSerializer(serializers.ModelSerializer):
    """Minimal competition details for nested serialization."""

    class Meta:
        model = models.Competition
        fields = ("id", "title", "slug")


class SeasonSerializer(serializers.ModelSerializer):
    """Minimal season details for nested serialization."""

    competition = CompetitionSerializer(read_only=True)

    class Meta:
        model = models.Season
        fields = ("id", "title", "slug", "competition")


class DivisionSerializer(serializers.ModelSerializer):
    """Minimal division details for nested serialization."""

    season = SeasonSerializer(read_only=True)

    class Meta:
        model = models.Division
        fields = ("id", "title", "slug", "season")


class StageSerializer(serializers.ModelSerializer):
    """Minimal stage details for nested serialization."""

    division = DivisionSerializer(read_only=True)

    class Meta:
        model = models.Stage
        fields = ("id", "title", "slug", "division")


class TeamSerializer(serializers.ModelSerializer):
    """Minimal team details for nested serialization."""

    club = ClubSerializer(read_only=True)

    class Meta:
        model = models.Team
        fields = ("id", "title", "slug", "club")


class LiveStreamMatchSerializer(serializers.ModelSerializer):
    """
    Serializer for matches with live streaming capabilities.

    Includes nested details of Stage, Division, Season, and Competition.
    """

    stage = StageSerializer(read_only=True)
    home_team = serializers.SerializerMethodField()
    away_team = serializers.SerializerMethodField()
    play_at = PlaceSerializer(read_only=True)
    round = serializers.SerializerMethodField()

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
            "stage",
            "play_at",
            "external_identifier",
            "live_stream",
            "live_stream_bind",
            "live_stream_thumbnail",
        )

    def get_round(self, obj):
        """Get round number or label."""
        return obj.label or f"Round {obj.round}"

    def _get_team(self, obj, home_or_away):
        """Get team data, handling undecided teams."""
        team = getattr(obj, f"get_{home_or_away}_team_plain")()
        if isinstance(team, (models.Team, models.ByeTeam)):
            if hasattr(team, "pk"):
                # Return full team data for decided teams
                return TeamSerializer(team, context=self.context).data
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

    Provides endpoints to list matches with live streaming capabilities,
    grouped by date, with optional filtering by date range and season.

    Also provides an endpoint to transition live stream status.
    """

    serializer_class = LiveStreamMatchSerializer
    lookup_field = "uuid"
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = LiveStreamMatchFilter

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

    def list(self, request, *args, **kwargs):
        """
        List matches grouped by date.

        Returns matches organized by their local date attribute for easier
        mobile UI consumption.
        """
        queryset = self.filter_queryset(self.get_queryset())

        # Group matches by date
        matches_by_date = {}
        for match in queryset:
            date_key = match.date.isoformat() if match.date else None
            if date_key:
                if date_key not in matches_by_date:
                    matches_by_date[date_key] = []
                matches_by_date[date_key].append(self.get_serializer(match).data)

        return Response(matches_by_date)

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
