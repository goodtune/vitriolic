from django.urls import include, path

from . import views

urlpatterns = [
    path("", views.v1_api_root, name="api-root"),
    path("news/", include(("touchtechnology.news.rest.v1.urls", "news"), namespace="news")),
    path("", include(("tournamentcontrol.competition.rest.v1.urls", "competition"), namespace="competition")),
]