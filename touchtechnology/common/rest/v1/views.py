from django.apps import apps
from django.urls.exceptions import NoReverseMatch
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse


@api_view(["GET"])
@permission_classes([AllowAny])
def v1_api_root(request, format=None):
    """
    The v1 TouchTechnology API root, showing all available endpoints.
    Dynamically discovers endpoints based on installed apps.
    """
    endpoints = {}

    # Add news API endpoints if the app is installed
    if apps.is_installed("touchtechnology.news"):
        try:
            endpoints["news"] = reverse(
                "v1:news:api-root", request=request, format=format
            )
        except NoReverseMatch:
            pass  # News app installed but API not available

    # Add competition API endpoints if the app is installed
    if apps.is_installed("tournamentcontrol.competition"):
        try:
            endpoints["clubs"] = reverse(
                "v1:competition:club-list", request=request, format=format
            )
            endpoints["competitions"] = reverse(
                "v1:competition:competition-list", request=request, format=format
            )
        except NoReverseMatch:
            pass  # Competition app installed but API not available

    return Response(endpoints)
