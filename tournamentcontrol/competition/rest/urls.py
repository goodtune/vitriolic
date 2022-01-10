from django.urls import include, path

urlpatterns = [
    path(
        "v1/",
        include(
            ("tournamentcontrol.competition.rest.v1.urls", "api"),
            namespace="v1",
        ),
    ),
    path("api-auth/", include("rest_framework.urls")),
]
