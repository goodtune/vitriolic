from django.apps import apps
from django.urls import include, path

from . import views

urlpatterns = [
    path("", views.v1_api_root, name="api-root"),
]

# Dynamically add API endpoints based on installed apps
if apps.is_installed("touchtechnology.news"):
    urlpatterns.append(
        path(
            "news/",
            include(("touchtechnology.news.rest.v1.urls", "news"), namespace="news"),
        )
    )

if apps.is_installed("tournamentcontrol.competition"):
    urlpatterns.append(
        path(
            "",
            include(
                ("tournamentcontrol.competition.rest.v1.urls", "competition"),
                namespace="competition",
            ),
        )
    )
