"""
Fail a test that shows a page of a list in no settled order.

The admin shows its lists a page at a time: a list page (``generic_list``), and
a tab of an object's page fetched on its own (``TOUCHTECHNOLOGY_HTMX_ADMIN_TABS``).
A page of a list in no settled order may repeat or skip an object from one
request to the next, which Django warns of with ``UnorderedObjectListWarning``.
Inside ``unordered_pages_fail`` the warning is an error, so the test fails::

    with unordered_pages_fail(), self.login(self.superuser):
        self.get("admin:news:category:list")
"""

import warnings
from contextlib import contextmanager

from django.core.paginator import UnorderedObjectListWarning


@contextmanager
def unordered_pages_fail():
    """Raise Django's warning that a list is paginated in no settled order."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", UnorderedObjectListWarning)
        yield
