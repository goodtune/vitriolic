from rest_framework import serializers
from tournamentcontrol.competition import models
from tournamentcontrol.competition.rest.v1.viewsets import SlugViewSet


class ClubSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = models.Club
        fields = (
            "title",
            "short_title",
            "slug",
            "abbreviation",
            "url",
            "facebook",
            "twitter",
            "youtube",
            "website",
        )
        read_only_fields = ("slug", "abbreviation")
        extra_kwargs = {"url": {"lookup_field": "slug"}}


class ClubViewSet(SlugViewSet):
    queryset = models.Club.objects.all()
    serializer_class = ClubSerializer
