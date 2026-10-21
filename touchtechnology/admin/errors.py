"""
The admin's own 403 and 404 pages.

Django answers ``PermissionDenied`` and ``Http404`` with the ``handler403`` and
``handler404`` of the *root* URL configuration, which by default render the
templates named ``403.html`` and ``404.html``. Those names belong to the public
site: a deployment's own pages, or the ones ``touchtechnology.common`` ships.
The admin must not ship pages under them, or which page a visitor is shown
would depend on the order of ``INSTALLED_APPS``, and the admin's page needs a
person who works in the admin to draw it.

So the admin answers the two for itself. ``ErrorPages`` stands between Django
and the views of an admin site and turns what they raise into the pages of the
site's shell (``Shell.not_found_template``, ``Shell.forbidden_template``), for
staff. Everyone else, and everything outside the admin, is left to the root
handlers and so to the public pages.

An address that no view of the admin answers never reaches the admin at all:
Django finds nothing to call and the root handler answers it.
"""

import functools

from asgiref.sync import iscoroutinefunction
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render
from django.urls import URLResolver
from django.urls.resolvers import RoutePattern


def is_staff(request):
    """Whether the person making the request works in the admin."""
    user = getattr(request, "user", None)
    return bool(user is not None and user.is_authenticated and user.is_staff)


class ErrorPages(URLResolver):
    """
    The URLs of an admin site, resolved as they would be without this class,
    with the view each one finds answering ``Http404`` and ``PermissionDenied``
    with the site's own pages when the request is a staff member's.
    """

    def __init__(self, patterns, site):
        super().__init__(RoutePattern("", is_endpoint=False), patterns)
        self.site = site

    def resolve(self, path):
        match = super().resolve(path)
        # A view that is a coroutine function must stay one.
        if not iscoroutinefunction(match.func):
            match.func = self.answer(match.func)
        return match

    def answer(self, view):
        @functools.wraps(view)
        def answered(request, *args, **kwargs):
            try:
                return view(request, *args, **kwargs)
            except Http404:
                # With debugging on Django describes the page that is missing.
                if settings.DEBUG or not is_staff(request):
                    raise
                return self.page(request, 404, self.site.shell.not_found_template)
            except PermissionDenied:
                if not is_staff(request):
                    raise
                return self.page(request, 403, self.site.shell.forbidden_template)

        return answered

    def page(self, request, status, template):
        context = {"admin": self.site, "shell": self.site.shell}
        return render(request, template, context, status=status)
