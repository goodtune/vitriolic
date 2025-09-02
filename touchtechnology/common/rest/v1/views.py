from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse


@api_view(['GET'])
def v1_api_root(request, format=None):
    """
    The v1 TouchTechnology API root, showing all available endpoints.
    """
    return Response({
        # News API endpoints
        'news': reverse('v1:news:api-root', request=request, format=format),
        
        # Competition API endpoints (at root level)
        'clubs': reverse('v1:competition:club-list', request=request, format=format),
        'competitions': reverse('v1:competition:competition-list', request=request, format=format),
    })