"""
Drive the tabs of an admin edit page the way a person does, in either tab mode.

An edit page lists its related objects in tabs. Traditionally every tab is in
the page; with ``TOUCHTECHNOLOGY_HTMX_ADMIN_TABS`` each tab is fetched the first
time it is shown. Whichever the mode, showing a tab must list the same objects,
so the helpers here read every tab of a page and the tests compare the modes.
"""

from playwright.sync_api import Page, expect

# What a tab says when the server could not work out what to put in it.
EMPTY_TAB = "No content available for this tab."


def set_mode(settings, htmx, paginate_by=25):
    """Choose the tab mode for the requests that follow."""
    settings.TOUCHTECHNOLOGY_HTMX_ADMIN_TABS = htmx
    settings.TOUCHTECHNOLOGY_HTMX_ADMIN_TAB_PAGINATE_BY = paginate_by


def tab_ids(page: Page):
    """The panes the tab navigation of the page leads to, in order."""
    return page.locator("#myTab a[data-toggle='tab']").evaluate_all(
        "links => links.map(a => a.getAttribute('href').slice(1))"
    )


def show_tab(page: Page, tab_id):
    """Show a tab and wait until its content is in the page."""
    page.locator(f"#myTab a[href='#{tab_id}']").click()
    pane = page.locator(f"#{tab_id}")
    expect(pane).to_be_visible()
    # A lazily loaded tab shows a spinner until its content arrives.
    expect(pane.locator(".fa-spinner")).to_have_count(0)
    return pane


def row_links(pane):
    """Where the rows of the list in a tab lead, as they appear in the page."""
    return pane.locator("tbody a[href]").evaluate_all(
        "links => links.map(a => a.getAttribute('href'))"
    )


class Tabs:
    """Everything a person sees in the tabs of one edit page."""

    def __init__(self, ids, links, errors):
        self.ids = ids
        self.links = links
        self.errors = errors

    def __repr__(self):
        return f"Tabs(ids={self.ids!r}, links={self.links!r})"


def read_tabs(page: Page, url):
    """
    Open an edit page, show each of its tabs in turn, and read what they list.

    Every tab must have content (never the empty fallback), and the page must
    raise no script errors on the way.
    """
    errors = []

    def record(error):
        errors.append(str(error))

    page.on("pageerror", record)
    page.goto(url)
    expect(page.locator("#myTab")).to_have_count(1)
    ids = tab_ids(page)
    links = {}
    for tab_id in ids[1:]:
        pane = show_tab(page, tab_id)
        expect(pane).not_to_contain_text(EMPTY_TAB)
        links[tab_id] = row_links(pane)
    page.remove_listener("pageerror", record)
    return Tabs(ids, links, errors)


def read_tabs_in_both_modes(page: Page, settings, url):
    """Read the tabs of a page traditionally and with HTMX tabs."""
    set_mode(settings, htmx=False)
    plain = read_tabs(page, url)
    set_mode(settings, htmx=True)
    lazy = read_tabs(page, url)
    return plain, lazy


def assert_same_in_both_modes(page: Page, settings, url):
    """The tabs of a page show the same objects whichever the mode."""
    plain, lazy = read_tabs_in_both_modes(page, settings, url)
    assert plain.errors == [], plain.errors
    assert lazy.errors == [], lazy.errors
    assert lazy.ids == plain.ids
    assert lazy.links == plain.links
    return plain
