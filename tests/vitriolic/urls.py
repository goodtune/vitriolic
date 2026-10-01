from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from oauth2_provider.urls import metadata_urlpatterns

from touchtechnology.admin.sites import site
from touchtechnology.common.sitemaps import NodeSitemap
from touchtechnology.common.sites import AccountsSite

accounts = AccountsSite()

urlpatterns = [
    path("admin/mcp/", include("tournamentcontrol.competition.mcp.admin.urls")),
    path("admin/", site.urls),
    path("accounts/", accounts.urls),
    path("mcp/", include("tournamentcontrol.competition.mcp.urls")),
    # The OAuth 2.0 authorization server; the RFC 8414 and RFC 9728
    # discovery documents are served from the site root.
    path("o/", include("oauth2_provider.urls", namespace="oauth2_provider")),
    path(
        "",
        include(
            (metadata_urlpatterns, "oauth2_provider"), namespace="oauth2_discovery"
        ),
    ),
    path("api/", include("touchtechnology.common.rest.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": {"nodes": NodeSitemap}}, name="sitemap"),
]
