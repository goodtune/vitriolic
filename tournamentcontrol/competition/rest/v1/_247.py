"""
LiveScore / LiveStream integration API resources.

This is not considered official API and should not be relied upon - it could change
at any time with changing needs.
"""

from rest_framework import serializers, viewsets

from tournamentcontrol.competition import models


class PlayerSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    division = serializers.ReadOnlyField(source="team.division.title")
    team = serializers.ReadOnlyField(source="team.title")
    name = serializers.SerializerMethodField(read_only=True)
    number = serializers.IntegerField(read_only=True)

    def get_name(self, obj):
        return f"{obj.person.first_name} {obj.person.last_name}".upper()


class PersonViewSet(viewsets.ModelViewSet):
    """
    This endpoint is used by the 247.tv developed application to seed it's
    list of players for use with the YouTube Event API for live streams.
    """

    lookup_field = "id"
    serializer_class = PlayerSerializer

    def get_queryset(self):
        return (
            models.TeamAssociation.objects.filter(
                team__division__season__slug=self.kwargs["season_slug"],
                team__division__season__competition__slug=self.kwargs[
                    "competition_slug"
                ],
                is_player=True,
            )
            .select_related("team__division", "team", "person")
            .order_by("team__division", "team", "number")
        )
