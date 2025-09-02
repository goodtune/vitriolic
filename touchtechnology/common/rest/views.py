from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse


@api_view(['GET'])
def api_root(request, format=None):
    """
    The root of the TouchTechnology API.
    """
    return Response({
        'v1': reverse('v1:api-root', request=request, format=format),
    })