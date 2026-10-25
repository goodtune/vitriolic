"""
Every delete confirmation in the admin names the thing it is about to delete.

Choosing Delete on a row asks first, in a dialog. Its title and its text have
to say which object is about to go, in words a person knows it by: the date of
an exclusion date, the title of a season. They must never say what Django says
of an object that has no ``__str__``, ``SeasonExclusionDate object (4)``.

There is a case (``tests/e2e/admin_delete.py``) for every delete route of the
admin. Each creates an object, opens the page that lists it, opens the menu of
its row, chooses Delete and reads the dialog. The words that the dialog must
use are written out in the table, not worked out from the code under test, so
a name that changes fails the test. Nothing is deleted: the check is about
what the dialog says.
"""

import re
from urllib.parse import urlparse

import cloudinary
import pytest
from django.urls import get_resolver, resolve
from playwright.sync_api import Page, expect

from tests.e2e.admin_delete import CASES, UNLINKED, Case
from tests.e2e.admin_tabs import show_tab
from tests.e2e.shells import CONFIRM_BODY, ROW_MENU, by_shell, pane_id

#: What Django calls an object that has no ``__str__``: ``Thing object (7)``.
DEFAULT_NAME = re.compile(r"object \(.*\)")


def delete_routes(resolver=None, namespace="admin"):
    """The namespaces of the admin that have a delete route, found in its URLs."""
    resolver = resolver or get_resolver().namespace_dict[namespace][1]
    found = set()
    if "delete" in resolver.reverse_dict:
        found.add(namespace)
    for name, (_, nested) in resolver.namespace_dict.items():
        found |= delete_routes(nested, f"{namespace}:{name}")
    return found


@pytest.fixture(autouse=True)
def cloudinary_credentials(monkeypatch):
    """A match page shows its score sheets, which Cloudinary signs the links to."""
    for name in ("cloud_name", "api_key", "api_secret"):
        monkeypatch.setattr(cloudinary.config(), name, "test", raising=False)


def says(case: Case):
    """The title and the text of the confirmation, in the shell the admin wears."""
    override = by_shell(workbook=case.workbook, explorer=case.explorer)
    if override:
        return override
    return (
        by_shell(workbook=f"Delete {case.name}?", explorer=f"Delete this {case.kind}?"),
        f"The {case.kind} “{case.name}” will be removed for good.",
    )


def test_every_delete_route_has_a_case():
    """
    A route that deletes is found in the admin's URLs, so a delete that is
    added to the admin has to be given a case before the suite passes, and a
    case has to say what its confirmation reads, so that a model added without
    a name of its own is not left with Django's.
    """
    covered = {case.route for case in CASES} | set(UNLINKED)
    assert delete_routes() == covered


def test_each_case_is_listed_once():
    """A case is named once, and a route is either linked to or it is not."""
    assert len({case.id for case in CASES}) == len(CASES)
    assert {case.route for case in CASES}.isdisjoint(UNLINKED)


@pytest.mark.parametrize("case", CASES, ids=repr)
def test_the_confirmation_names_the_object(
    authenticated_page: Page, live_server, settings, tmp_path, screenshot_dir, case
):
    """
    Open the page that lists the object, open the menu of its row and choose
    Delete: the dialog that asks first says which object it is, by the name
    the table gives it, never by Django's default ``Thing object (7)``.
    """
    settings.MEDIA_ROOT = tmp_path
    opening = case.make()
    page = authenticated_page
    page.goto(f"{live_server.url}{opening.path}")
    scope = show_tab(page, pane_id(opening.tab)) if opening.tab else page
    rows = scope.locator("tbody tr")
    row = rows.filter(has_text=opening.row) if opening.row else rows
    expect(row).to_have_count(1)

    row.get_by_role("button", name=ROW_MENU).click()
    delete = row.get_by_role("button", name="Delete", exact=True)
    expect(delete).to_be_visible()
    # The row posts to the route the case is for.
    action = urlparse(delete.locator("xpath=ancestor::form").get_attribute("action"))
    assert resolve(action.path).namespace == case.route
    delete.click()

    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    page.screenshot(path=screenshot_dir / f"delete_modal_{case.id}.png")
    title, text = says(case)
    expect(dialog.get_by_role("heading")).to_have_text(title)
    expect(dialog.locator(CONFIRM_BODY)).to_have_text(text)
    expect(dialog).not_to_contain_text(DEFAULT_NAME)
