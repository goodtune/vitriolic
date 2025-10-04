from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse


@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request, format=None):
    """
    The root of the TouchTechnology API.
    """
    return Response(
        {
            "v1": reverse("v1:api-root", request=request, format=format),
        }
    )
