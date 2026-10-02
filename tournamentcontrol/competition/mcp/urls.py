from django.urls import path

from tournamentcontrol.competition.mcp.views import MCPView

urlpatterns = [
    path("", MCPView.as_view(), name="mcp"),
]
