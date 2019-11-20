from django.conf.urls import url
from django.contrib.sitemaps.views import sitemap
from touchtechnology.admin.sites import site
from touchtechnology.common.sitemaps import NodeSitemap
from touchtechnology.common.sites import AccountsSite

accounts = AccountsSite()

urlpatterns = [
    url(r"^admin/", site.urls),
    url(r"^accounts/", accounts.urls),
    url(
        r"^sitemap\.xml$", sitemap, {"sitemaps": {"nodes": NodeSitemap}}, name="sitemap"
    ),
]
