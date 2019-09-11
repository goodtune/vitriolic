from django.conf.urls import include, url

urlpatterns = [
    url(r"v1/", include("tournamentcontrol.competition.rest.v1.urls", namespace="v1")),
    url(r"^api-auth/", include("rest_framework.urls")),
]
