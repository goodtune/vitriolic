"""
Serve the admin as a multi-tenant installation does.

``django-tenant-schemas`` gives every request a ``tenant`` and points the
database connection at that tenant's schema; outside a request, its
``schema_context`` and ``tenant_context`` point the connection. The admin
changes what it does when a request has a tenant (see
``AdminComponentMixin.render``), and the content app keeps the URL tree of
each schema apart. The test project is single-tenant, so a test that is about
that case decorates its test case with ``@as_tenant``::

    @as_tenant
    class SomePageTests(TestCase):
        ...

and a test that needs more than one tenant chooses one with
``schema_context``::

    with schema_context("alpha"):
        self.get(...)
"""

from types import SimpleNamespace
from unittest import mock

from django.db import DEFAULT_DB_ALIAS, connection, connections
from django.test import modify_settings


class TenantMiddleware:
    """
    Gives each request a ``tenant``, as ``django-tenant-schemas`` does.

    The real middleware finds the tenant from the host and points the
    connection at its schema, so the two always agree during a request. The
    test database has one schema, so a test chooses the tenant with
    ``schema_context`` and the request is given that one, or ``public``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = SimpleNamespace(
            schema_name=getattr(connection, "schema_name", "public"),
            domain_url="testserver",
        )
        return self.get_response(request)


def as_tenant(cls):
    """
    Run each test of ``cls`` with every request having a ``tenant``.

    The middleware goes first, as ``touchtechnology.admin`` requires of the
    real one, so every other middleware sees the tenant.
    """
    return modify_settings(MIDDLEWARE={"prepend": f"{__name__}.TenantMiddleware"})(cls)


def schema_context(schema_name):
    """
    Point the connection at a tenant's schema, as
    ``tenant_schemas.utils.schema_context`` does.
    """
    return mock.patch.object(
        connections[DEFAULT_DB_ALIAS], "schema_name", schema_name, create=True
    )
