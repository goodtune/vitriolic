"""
The demo project's URLs with pages that fail, for the error page tests.

``missing`` and ``forbidden`` are a public site's pages that raise ``Http404``
and ``PermissionDenied``. ``errors`` is an admin site with the same two pages
inside it, so the tests can say what a person sees when the admin itself
refuses them.
"""

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import path
from vitriolic.urls import urlpatterns as project_urlpatterns

from touchtechnology.admin.sites import AdminSite


def missing(request):
    raise Http404


def forbidden(request):
    raise PermissionDenied


class ErrorsAdminSite(AdminSite):
    def get_urls(self):
        return super().get_urls() + [
            path("missing/", missing, name="missing"),
            path("forbidden/", forbidden, name="forbidden"),
        ]


errors_site = ErrorsAdminSite(name="errors")

urlpatterns = [
    path("missing/", missing, name="missing"),
    path("forbidden/", forbidden, name="forbidden"),
    path("errors-admin/", errors_site.urls),
    *project_urlpatterns,
]
