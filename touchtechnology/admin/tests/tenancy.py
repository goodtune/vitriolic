"""
Serve the admin as a multi-tenant installation does.

``django-tenant-schemas`` gives every request a ``tenant``, and the admin
changes what it does when a request has one (see ``AdminComponentMixin.render``).
The test project is single-tenant, so a test that is about that case decorates
its test case with ``@as_tenant``::

    @as_tenant
    class SomePageTests(TestCase):
        ...
"""

from types import SimpleNamespace

from django.test import modify_settings


class TenantMiddleware:
    """Gives each request a ``tenant``, as ``django-tenant-schemas`` does."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = SimpleNamespace(schema_name="public", domain_url="testserver")
        return self.get_response(request)


def as_tenant(cls):
    """Run each test of ``cls`` with every request having a ``tenant``."""
    return modify_settings(MIDDLEWARE={"append": f"{__name__}.TenantMiddleware"})(cls)
