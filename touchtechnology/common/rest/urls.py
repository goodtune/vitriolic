from django.urls import include, path

from . import views

urlpatterns = [
    path("", views.api_root, name="api-root"),
    path("v1/", include(("touchtechnology.common.rest.v1.urls", "v1"), namespace="v1")),
    path("api-auth/", include("rest_framework.urls")),
]
