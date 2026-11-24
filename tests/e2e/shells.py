"""
What the browser tests look for, in whichever shell the admin is wearing.

The shell is chosen by the environment variable ``ADMIN_SHELL``, as the demo
project does (``tests/vitriolic/urls.py``), so the browser tests run once
under each: ``ADMIN_SHELL=explorer`` for the second pass.
"""

import os
import re

SHELL = os.environ.get("ADMIN_SHELL", "workbook")


def by_shell(*, workbook, explorer):
    """The value for the shell the admin is wearing."""
    return {"workbook": workbook, "explorer": explorer}[SHELL]


#: The ending of the id of a tab's pane, after the tab's name.
PANE = by_shell(workbook="-pane", explorer="-tab")
#: The list of tabs of an edit page.
TABLIST = by_shell(workbook="[role=tablist]", explorer="[role=tablist][data-tabs]")
#: What a pane says while its content is being fetched.
LOADING = by_shell(workbook=".wb-pane-loading", explorer=".pane-loading")
#: The links that act on the list in a tab (add another, and the like).
LIST_ACTIONS = by_shell(
    workbook=".wb-sheet-head .wb-actions a[href]",
    explorer=".list-head .list-actions a[href]",
)
#: The panes of an edit page that are fetched when first shown.
LAZY_PANES = by_shell(workbook=".wb-pane[hx-get]", explorer="[data-tab-panel][hx-get]")
#: The panes that wait to be shown, and what makes them fetch their content.
LAZY_ONCE = by_shell(
    workbook='.wb-pane[hx-trigger="intersect once"]',
    explorer='[data-tab-panel][hx-trigger="shown once"]',
)
#: The form inside the pane on show.
ACTIVE_FORM = by_shell(
    workbook=".wb-pane:not([hidden]) form.wb-form",
    explorer="[data-tab-panel].is-active form#edit-form",
)
#: The form of an edit page.
EDIT_FORM = by_shell(workbook="form.wb-form", explorer="form#edit-form")
#: The Save button of the page's form.
SAVE = by_shell(
    workbook='.wb-pane:not([hidden]) .wb-formbar button[type="submit"]',
    explorer='.form-buttons button[type="submit"]',
)
#: The page numbers under a list.
PAGER = by_shell(workbook=".wb-pagination", explorer=".pager")
#: The current page number of a pager.
PAGER_CURRENT = by_shell(workbook="[aria-current]", explorer="[aria-current=page]")
#: The explanation under a field.
FIELD_HELP = by_shell(workbook="p.wb-help", explorer="p.field-help")
#: A field with an error.
HAS_ERROR = by_shell(workbook=".wb-has-error", explorer=".has-error")


def pane_id(name):
    """The id of the pane of the tab called ``name``."""
    return name + PANE


def tab_control(pane_id):
    """The selector of the control that shows the pane with id ``pane_id``."""
    return by_shell(
        workbook=f"[role=tab][aria-controls='{pane_id}']",
        explorer=f"a[href='#{pane_id}']",
    )


def tab_link(name):
    """The selector of the control that shows the tab called ``name``."""
    return tab_control(pane_id(name))


#: The headings of the cards on the home page.
WIDGET_HEADINGS = by_shell(workbook="section.wb-widget h2", explorer="main .card > h2")

#: The name of the button that opens the menu of actions of a row.
ROW_MENU = re.compile(by_shell(workbook="More actions", explorer="^More actions for"))
#: What the dialog that asks before something is deleted says, under its heading.
CONFIRM_BODY = by_shell(workbook="[data-wb-confirm-text]", explorer="#confirm-body")

#: The rows of the bulk-create page.
BULK_ROWS = by_shell(workbook=".wb-bulk-row", explorer="table.bulk-table tbody tr")
#: The rows of the live-stream form of a match day.
LIVE_STREAM_ROWS = by_shell(workbook="form table tbody tr", explorer=".live-stream-row")
