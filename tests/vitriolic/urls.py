from django.contrib.sitemaps.views import sitemap
from django.urls import path

from touchtechnology.admin.sites import site
from touchtechnology.common.sitemaps import NodeSitemap
from touchtechnology.common.sites import AccountsSite

accounts = AccountsSite()

urlpatterns = [
    path("admin/", site.urls),
    path("accounts/", accounts.urls),
    path("sitemap.xml", sitemap, {"sitemaps": {"nodes": NodeSitemap}}, name="sitemap"),
]
