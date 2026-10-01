from django.urls import path

from tournamentcontrol.competition.mcp.views import AdminMCPView

urlpatterns = [
    path("", AdminMCPView.as_view(), name="mcp-admin"),
]
