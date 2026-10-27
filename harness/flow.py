"""An administrator's errand through the whole admin, for the video.

The flow signs in and then builds a small competition from nothing, running
it through a draw, a schedule and results, adds news and pages, runs a school
enrolment and signs out. Each of the thirteen ``step_<n>_<name>`` functions is
one stretch of that errand and returns how it got where it was going:

``"link"``    every move followed a link, button or menu the page offered;
``"scroll"``  the same, but the link or button that changes the page, or opens
              the tab, was out of view and had to be scrolled to first;
``"direct"``  the address was typed, because the page offered no way there.

The flow must survive an admin whose markup has been rewritten, so it looks
for things the way a person (or a screen reader) does: by role and accessible
name (``get_by_role``), by visible text (``get_by_text``), by the target of a
link (``a[href=...]``) and by the name of a form field (``[name=...]``,
``get_by_label``). It never looks for an id, a class or a data attribute
first. The few that today's markup needs are in ``LEGACY_FALLBACKS``, read
only by ``legacy_fallback`` and only after every lookup by role, text, link
target and field name has failed.

A step whose target cannot be found by any of those records ``via: direct``
with a one-line note naming what it looked for, goes to the address, and goes
on; that is evidence about the admin, not a failure. A step fails, and the
run with it, on an uncaught page error, a console error, a failed request to
the server under test, or a failed assertion, such as a saved title that is
not on the page it returned to.

Everything the flow creates has an invented name ending in the run stamp, so
repeated runs never collide, and ``python -m harness unflow <stamp>`` removes
it again. A headless recording shows no pointer, so the target of every click
is ringed for a moment first.
"""

import datetime
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

from django.conf import global_settings
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from harness.images import photo
from harness.manifest import Manifest, StepResult

logger = logging.getLogger(__name__)

LOGIN_PATH = "/admin/login/"
LOGOUT_PATH = "/admin/logout/"
USERNAME = "admin"
PASSWORD = "password"

#: Below this width the main menu is folded away behind a button.
NARROW = 768

#: How long the ring stays on a target before the click, so a video shows it.
PAUSE_MS = 300
#: How long to wait for something the page should already be showing.
VISIBLE_MS = 5000
SETTLE_MS = 3000
NAVIGATION_MS = 30000
TYPING_DELAY_MS = 12
#: How long to look for something that may be a moment in appearing.
LOOK_MS = 700
#: How long to look for a dialog the last click should have opened.
DIALOG_WAIT_S = 1.5

#: The menu entries and the admin pages the flow passes through.
COMPETITIONS = "/admin/fixja/competition/"
CLUBS = "/admin/fixja/club/"
SITEMAP = "/admin/content/"
REDIRECTS = "/admin/content/redirect/"
NEWS_CATEGORIES = "/admin/news/category/"
NEWS_ARTICLES = "/admin/news/article/"
DRAW_FORMATS = "/admin/fixja/draw-format/"
ENROLMENT_YEARS = "/admin/enrolment/year/"
ENROLMENT_GRADES = "/admin/enrolment/grade/"
ENROLMENT_STUDENTS = "/admin/enrolment/student/"
ENROLMENT_TEACHERS = "/admin/enrolment/teacher/"

RING_SCRIPT = """el => {
    if (window.__ring && window.__ring !== el) {
        window.__ring.style.outline = window.__ringWas;
    }
    if (window.__ring !== el) {
        window.__ringWas = el.style.outline;
    }
    window.__ring = el;
    el.style.outline = '3px solid #e5322d';
    el.style.outlineOffset = '2px';
}"""

IN_VIEW_SCRIPT = """el => {
    const r = el.getBoundingClientRect();
    return r.top >= 0 && r.left >= 0
        && r.bottom <= window.innerHeight && r.right <= window.innerWidth;
}"""

SELECTED_TEXT_SCRIPT = (
    "el => el.selectedIndex < 0 ? '' : el.options[el.selectedIndex].text"
)

#: What today's admin needs that no role, text, link target or field name
#: can reach. Read only by ``legacy_fallback``, which is called only after
#: every lookup by role, text, link target and field name has found nothing.
#: Nothing outside this mapping may name an id, a class or a ``data-``
#: attribute (``test_flow.py`` checks).
LEGACY_FALLBACKS = {
    # A tab of an edit page, in the sidebar list of tabs.
    "tab": '#myTab a[href="#{tab}-tab"]',
    # The two buttons that fold open the menus below the narrow breakpoint.
    "main_menu_toggle": 'a[data-target=".mainnav-collapse"]',
    "banner_menu_toggle": 'button[data-target=".navbar-collapse"]',
    # The signed-in user's drop-down in the banner.
    "profile_menu": 'header a[data-toggle="dropdown"]',
    # The drop-down of a table row's actions.
    "row_menu": 'button[data-toggle="dropdown"]',
    # The button of a stage's row that undoes its draw.
    "row_undo": 'a[data-action$="/undo/"]',
    # A select dressed up by Select2 version 3.
    "select2": '[id="s2id_{id}"]',
}


def legacy_fallback(scope: Page | Locator, key: str, **fields: str) -> Locator:
    """
    The one place ``LEGACY_FALLBACKS`` is read: the locator for ``key`` inside
    ``scope``, with ``fields`` filled into its selector.
    """
    return scope.locator(LEGACY_FALLBACKS[key].format(**fields))


#: Page errors the baseline admin raises that the flow passes through, by the
#: exact text of the error. Each is recorded as a warning with its text on
#: the step that met it, so that a recording of the baseline reaches the end.
#: Any other uncaught page error fails the step.
KNOWN_PAGE_ERRORS = {
    "Cannot set properties of undefined (setting '_DT_CellIndex')": (
        "known baseline error: the club edit page runs DataTables on every "
        "table, and DataTables 1.10 cannot take the colspan cell of an empty "
        "list (club/edit.html prepareTables, list.inc.html table-row-empty)"
    ),
}
PAGE_ERROR_PREFIX = "uncaught page error: "

#: A round robin of four teams, in the draw format syntax.
ROUND_ROBIN_FOUR = (
    "ROUND\n1: 1 vs 4\n2: 2 vs 3\n"
    "ROUND\n3: 1 vs 3\n4: 4 vs 2\n"
    "ROUND\n5: 1 vs 2\n6: 3 vs 4"
)

#: The invented place of the flow's venue: latitude, longitude and zoom.
VENUE_PLACE = ("-35.0200", "150.0400", "15")
#: A telephone number from the range reserved for fiction.
GUARDIAN_PHONE = "0491 570 156"

#: Rank of the ways a step can reach a page; the worst one is the step's.
RANK = {"link": 0, "scroll": 1, "direct": 2}

#: What each tab of an edit page says. The flow knows a tab by its key; a
#: person knows it by its label.
TAB_LABELS = {
    "seasons": "Seasons",
    "club_roles": "Club roles",
    "team_roles": "Team roles",
    "exclusions": "Exclusion dates",
    "timeslots": "Time slots",
    "venues": "Venues",
    "grounds": "Grounds",
    "referees": "Referees",
    "divisions": "Divisions",
    "schedule": "Schedule",
    "members": "People",
    "teams": "Teams",
    "stages": "Stages",
    "pools": "Pools",
    "undecided_teams": "Undecided teams",
    "people": "Linked people",
    "translations": "Translations",
    "classes": "Class groups",
    "enrolments": "Enrolments",
    "assessments": "Assessments",
    "attendance": "Attendance records",
    "report_cards": "Report cards",
}

#: The names a control that folds a menu open commonly has.
MENU_NAMES = re.compile(r"toggle navigation|navigation|menu", re.I)
#: The signed-in user's menu: the user's address, or a profile or account.
PROFILE_NAMES = re.compile(r"@|profile|account|\badmin\b", re.I)
LOGOUT_NAMES = re.compile(r"log ?out|sign ?out", re.I)
#: The row actions' opener, when it has a name at all.
ROW_MENU_NAMES = re.compile(r"actions|more|options|menu", re.I)
#: A button that confirms what a dialog asks, and one that only continues.
CONFIRM_NAMES = re.compile(r"delete|undo|remove|confirm|yes", re.I)
CONTINUE_NAMES = re.compile(r"continue|ok|go|next|add", re.I)
UNDO_NAMES = re.compile(r"undo", re.I)
DELETE_NAMES = re.compile(r"delete|remove", re.I)
#: Words that mark a link as the one that adds something.
ADD_WORDS = re.compile(r"add|new|create", re.I)

#: Django's own settings, which the demo project does not override.
DATE_INPUT_FORMAT = global_settings.DATE_INPUT_FORMATS[0]
DATETIME_INPUT_FORMAT = global_settings.DATETIME_INPUT_FORMATS[0]


_PLACEHOLDER_TOKENS = {
    "d": "%d",
    "dd": "%d",
    "m": "%m",
    "mm": "%m",
    "yy": "%y",
    "yyyy": "%Y",
}


def format_date(
    day: datetime.date,
    kind: str = "text",
    placeholder: str = "",
    when: datetime.time | None = None,
) -> str:
    """
    ``day`` (and ``when``) as the field accepts it. The input's ``type`` says
    first (``date``, ``datetime-local`` and ``time`` take ISO forms); a text
    field's placeholder is read when it looks like ``dd/mm/yyyy``; otherwise
    Django's first date (or date and time) input format is used, which the
    demo project does not override.
    """
    if kind == "date":
        return day.isoformat()
    if kind == "datetime-local":
        return datetime.datetime.combine(day, when or datetime.time(0)).strftime(
            "%Y-%m-%dT%H:%M"
        )
    if kind == "time":
        return (when or datetime.time(0)).strftime("%H:%M")
    layout = DATE_INPUT_FORMAT
    pattern = re.fullmatch(r"\s*([dmy]+)(\W)([dmy]+)(\W)([dmy]+)\s*", placeholder, re.I)
    if pattern:
        parts = [_PLACEHOLDER_TOKENS.get(pattern.group(n).lower()) for n in (1, 3, 5)]
        if all(parts) and len(set(parts)) == 3:
            layout = (
                parts[0] + pattern.group(2) + parts[1] + pattern.group(4) + parts[2]
            )
    if when is None:
        return day.strftime(layout)
    if layout == DATE_INPUT_FORMAT:
        return datetime.datetime.combine(day, when).strftime(DATETIME_INPUT_FORMAT)
    return datetime.datetime.combine(day, when).strftime(layout + " %H:%M")


def date_pattern(day: datetime.date) -> re.Pattern:
    """
    A pattern for ``day`` written any of the usual ways, so that a check does
    not depend on Django's list format (``Oct. 14, 2026``).
    """

    def number(value: int) -> str:
        return rf"(?<!\d)0?{value}(?!\d)"

    full, abbreviation = day.strftime("%B"), day.strftime("%b")
    names = {re.escape(full), re.escape(abbreviation) + r"\.?"}
    if day.month == 9:
        names.add(r"Sept\.?")
    word = f"(?:{'|'.join(sorted(names))})"
    month, mday = number(day.month), number(day.day)
    forms = [
        rf"{day.year}-{month}-{mday}",
        rf"{mday}\W+{month}\W+{day.year}",
        rf"{month}\W+{mday}\W+{day.year}",
        rf"{mday}\W+{word}\W+{day.year}",
        rf"{word}\W+{mday}\W+{day.year}",
    ]
    return re.compile("|".join(f"(?:{form})" for form in forms), re.I)


def time_pattern(when: datetime.time) -> re.Pattern:
    """A pattern for ``when`` as 18:00, 6 p.m., 6:00 PM and the like."""
    twelve = when.hour % 12 or 12
    meridiem = "a" if when.hour < 12 else "p"
    if when.minute:
        clock = f"{twelve}:{when.minute:02d}"
    else:
        clock = f"{twelve}(?::00)?"
    return re.compile(
        rf"{when.hour:02d}:{when.minute:02d}|(?<!\d){clock}\s*{meridiem}\.?m\.?",
        re.I,
    )


@dataclass
class State:
    """What the steps share: the page, the run stamp and what they made."""

    page: Page
    base: str
    width: int
    stamp: str
    today: datetime.date
    data: dict = field(default_factory=dict)
    via: str = "link"
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def narrow(self) -> bool:
        return self.width < NARROW

    def begin(self) -> None:
        self.via = "link"
        self.notes = []
        self.warnings = []

    def reach(self, how: str) -> None:
        """Record that a move needed ``how``, keeping the worst so far."""
        if RANK[how] > RANK[self.via]:
            self.via = how

    def direct(self, reason: str) -> None:
        self.reach("direct")
        self.notes.append(reason)
        self.warnings.append(f"went direct: {reason}")

    def skip(self, reason: str) -> None:
        """Record something the errand cannot do in today's admin."""
        self.notes.append(f"not exercised: {reason}")
        self.warnings.append(f"not exercised: {reason}")

    def workaround(self, reason: str) -> None:
        """Record a fault of today's admin that the errand steps around."""
        self.notes.append(f"workaround: {reason}")
        self.warnings.append(f"workaround: {reason}")

    def name(self, text: str) -> str:
        """An invented name for an object: ``text`` and the run stamp."""
        return f"{text} {self.stamp}"

    def date(self, days: int) -> datetime.date:
        return self.today + datetime.timedelta(days=days)

    @property
    def year(self) -> str:
        """
        The title of the flow's school year: at most four characters, unique,
        and never one of the seeded years, which all begin with a 2.
        """
        return "9" + self.stamp[-3:]


# --------------------------------------------------------------------------
# What a person does with a page.


def settle(page: Page) -> None:
    """Wait for the page to load and the network to go quiet, but not long."""
    page.wait_for_load_state("load", timeout=NAVIGATION_MS)
    try:
        page.wait_for_load_state("networkidle", timeout=SETTLE_MS)
    except PlaywrightTimeout:
        logger.debug("%s did not go idle in %d ms", page.url, SETTLE_MS)


def path_of(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path


def first_visible(*candidates: Locator, wait_ms: int = LOOK_MS) -> Locator | None:
    """
    The first visible match of the first candidate that has one, or ``None``
    once ``wait_ms`` has passed without any: what a person looks for may be
    a moment in appearing.
    """
    deadline = time.monotonic() + wait_ms / 1000
    while True:
        for candidate in candidates:
            visible = candidate.filter(visible=True)
            if visible.count():
                return visible.first
        if time.monotonic() >= deadline:
            return None
        candidates[0].page.wait_for_timeout(100)


def each(locator: Locator) -> list[Locator]:
    """Every match of ``locator``, one locator each, in page order."""
    return [locator.nth(i) for i in range(locator.count())]


def quoted(text: str) -> str:
    """``text`` as the value of an attribute selector."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def aim(state: State, target: Locator, nav: bool = False) -> Locator:
    """
    Bring ``target`` into view, ring it and hold still for a moment. Having to
    scroll is recorded, since a person has to do it too, but only when
    ``nav`` says the target is what changes the page or opens the tab: the
    Save button at the foot of a long form counts, a field in it does not.
    """
    target = target.filter(visible=True).first
    target.wait_for(state="visible", timeout=VISIBLE_MS)
    if not target.evaluate(IN_VIEW_SCRIPT):
        if nav:
            state.reach("scroll")
        target.scroll_into_view_if_needed()
    target.evaluate(RING_SCRIPT)
    state.page.wait_for_timeout(PAUSE_MS)
    return target


def click(state: State, target: Locator, nav: bool = True) -> None:
    """Click ``target``; by default it is the way to another page or tab."""
    aim(state, target, nav).click()
    settle(state.page)


def visible_field(state: State, name: str) -> Locator:
    """The visible form field called ``name``."""
    return state.page.locator(f"[name={quoted(name)}]").filter(visible=True).first


def fill_field(target: Locator, text: str, force: bool = False) -> None:
    """Type ``text`` into ``target`` the way a person does, or paste long text."""
    kind = (target.get_attribute("type") or "text").lower()
    target.fill("")
    if len(text) <= 60 and not force and kind not in DATE_KINDS:
        target.press_sequentially(text, delay=TYPING_DELAY_MS)
    else:
        target.fill(text)


#: Inputs a browser fills in from a form of the date, not from key presses.
DATE_KINDS = ("date", "datetime-local", "time")


def type_into(state: State, name: str, text: str, force: bool = False) -> None:
    """Type ``text`` into the visible field called ``name``."""
    target = aim(state, visible_field(state, name))
    fill_field(target, text, force)


def type_date(
    state: State, name: str, day: datetime.date, when: datetime.time | None = None
) -> None:
    """
    Type ``day`` into the date field called ``name`` in the form the field
    accepts: its ``type`` and placeholder say which.
    """
    target = aim(state, visible_field(state, name))
    kind = (target.get_attribute("type") or "text").lower()
    placeholder = target.get_attribute("placeholder") or ""
    fill_field(target, format_date(day, kind, placeholder, when))


def attach(state: State, name: str, picture) -> None:
    """Give the file field called ``name`` a picture (a Django ``ContentFile``)."""
    target = state.page.locator(f'input[type="file"][name={quoted(name)}]')
    aim(state, target)
    target.set_input_files(
        {
            "name": picture.name,
            "mimeType": "image/jpeg",
            "buffer": picture.read(),
        }
    )
    state.page.wait_for_timeout(PAUSE_MS)


def label_of(state: State, field: Locator) -> str:
    """What the form calls ``field``: the text of the label that points to it."""
    field_id = field.get_attribute("id")
    if not field_id:
        return ""
    label = state.page.locator(f"label[for={quoted(field_id)}]").first
    return " ".join(label.text_content().split()) if label.count() else ""


def choose(state: State, name: str, text: str) -> None:
    """
    Pick the option of the field called ``name`` that shows ``text``. A select
    that is on show is used as it stands. One that the admin has dressed as
    something else is found by its label as a combobox; failing that, by the
    widget's own markup (``LEGACY_FALLBACKS``); failing that, the select
    behind it is set and the step says so.
    """
    page = state.page
    native = page.locator(f"select[name={quoted(name)}]").first
    if native.is_visible():
        aim(state, native)
        label = native.locator("option", has_text=text).first.text_content()
        native.select_option(label=label)
        return
    multiple = native.get_attribute("multiple") is not None
    label = label_of(state, native)
    widget = None
    if label:
        widget = first_visible(page.get_by_role("combobox", name=label))
    if widget is None:
        field_id = native.get_attribute("id") or ""
        container = legacy_fallback(page, "select2", id=field_id)
        if container.count():
            # A multiple choice is opened from its search box; the first link
            # in it would be the cross that removes a choice already made.
            widget = container.locator("input" if multiple else "a").first
    if widget is None:
        value = native.locator("option", has_text=text).first.get_attribute("value")
        chosen = native.evaluate(
            "el => Array.from(el.selectedOptions).map(o => o.value)"
        )
        values = [*chosen, value] if multiple else [value]
        native.select_option(value=values, force=True)
        state.workaround(
            f"the {name} field is hidden behind a widget the flow cannot find by label "
            "or role, so its select was set directly"
        )
        return
    aim(state, widget).click()
    page.keyboard.type(text, delay=TYPING_DELAY_MS)
    page.wait_for_timeout(PAUSE_MS)
    page.keyboard.press("Enter")
    page.wait_for_timeout(PAUSE_MS)


def reveal(
    state: State,
    find: Callable[[], Locator | None],
    candidates: Callable[[], list[Locator]],
    limit: int = 6,
) -> Locator | None:
    """
    What ``find`` looks for, after opening whatever hides it. Each control in
    ``candidates()`` is tried once, in turn, and ``find`` is asked again after
    every click. Nothing found is ``None``, and the caller goes direct.
    """
    tried: set[int] = set()
    for __ in range(limit):
        found = find()
        if found is not None:
            return found
        for candidate in candidates():
            # Its place in the document, which does not move when the page
            # scrolls, as its position on the screen does.
            key = candidate.evaluate(
                "el => Array.from(document.getElementsByTagName('*')).indexOf(el)"
            )
            if key in tried:
                continue
            tried.add(key)
            click(state, candidate)
            break
        else:
            break
    return find()


IN_BANNER_SCRIPT = "el => el.closest('header, [role=banner]') !== null"


def menu_togglers(page: Page, banner_first: bool = False) -> list[Locator]:
    """
    The controls that may fold a collapsed menu open, the likeliest first:
    buttons named like a menu, anything that says so in its text, buttons that
    report whether they are expanded (the ones in a table row open that row's
    own menu and are left alone), and last the legacy buttons. The one in the
    banner usually opens the banner's own menu, the signed-in user's, so it
    comes after the others, or before them when ``banner_first`` says so.
    """
    found = [
        *each(page.get_by_role("button", name=MENU_NAMES).filter(visible=True)),
        *each(
            page.locator("a, button").filter(has_text=MENU_NAMES).filter(visible=True)
        ),
        *each(
            page.locator('button[aria-expanded="false"]:not(tr button)').filter(
                visible=True
            )
        ),
        *each(legacy_fallback(page, "main_menu_toggle").filter(visible=True)),
        *each(legacy_fallback(page, "banner_menu_toggle").filter(visible=True)),
    ]
    banner = [toggle.evaluate(IN_BANNER_SCRIPT) for toggle in found]
    return [
        toggle
        for __, toggle in sorted(
            zip(banner, found), key=lambda pair: pair[0] != banner_first
        )
    ]


def profile_togglers(page: Page) -> list[Locator]:
    """The menu togglers, banner first, and then what opens the user's menu."""
    togglers = menu_togglers(page, banner_first=True)
    return [
        *togglers[:1],
        *each(page.get_by_role("link", name=PROFILE_NAMES).filter(visible=True)),
        *each(page.get_by_role("button", name=PROFILE_NAMES).filter(visible=True)),
        *each(legacy_fallback(page, "profile_menu").filter(visible=True)),
        *togglers[1:],
    ]


def search(state: State, text: str) -> None:
    """Look ``text`` up with the search box of a long list."""
    page = state.page

    def box() -> Locator | None:
        return first_visible(page.locator('[name="search"]'))

    # At a phone's width the search box is folded away with the menu.
    if box() is None:
        reveal(state, box, lambda: menu_togglers(page))
    type_into(state, "search", text)
    with page.expect_navigation(wait_until="load"):
        page.keyboard.press("Enter")
    settle(page)


def save(state: State) -> None:
    click(state, state.page.get_by_role("button", name="Save", exact=True))


def cancel(state: State) -> None:
    click(state, state.page.get_by_role("link", name="Cancel", exact=True))


def see(state: State, text: str | re.Pattern, tab: str | None = None) -> None:
    """
    Check that ``text`` is on the page, as a person would look: in the page's
    text or, for a string, in a field of its form. A page that comes back
    showing another tab is shown the tab the object is listed in. It raises
    when the text is not there.
    """
    page = state.page

    def shown() -> Locator:
        in_text = page.get_by_text(text).filter(visible=True)
        if isinstance(text, re.Pattern):
            return in_text
        in_field = page.locator(f"input[value={quoted(text)}]").filter(visible=True)
        return in_text.or_(in_field)

    if tab and shown().count() == 0:
        open_tab(state, tab)
    try:
        shown().first.wait_for(state="visible", timeout=VISIBLE_MS)
        return
    except PlaywrightTimeout:
        pass
    # Lists are paged, and an object made on a database that has been used
    # before is not on the first page: turn the pages until it shows.
    pages = (
        page.locator('a[href^="?page="]')
        .filter(visible=True)
        .evaluate_all("links => links.map(a => a.getAttribute('href'))")
    )
    for href in pages:
        click(state, page.locator(f"a[href={quoted(href)}]"))
        try:
            shown().first.wait_for(state="visible", timeout=VISIBLE_MS)
            return
        except PlaywrightTimeout:
            continue
    raise AssertionError(f"{getattr(text, 'pattern', text)!r} is not on {page.url}")


def find_tab(state: State, key: str) -> Locator | None:
    """
    The tab called ``key``, found by the label a person reads: a ``tab`` by
    name, a link of that name in a ``tablist``, a link to an anchor of the
    page, any link or button of that name, and last the legacy list of tabs.
    """
    page = state.page
    label = TAB_LABELS.get(key, key.replace("_", " ").capitalize())
    name = re.compile(rf"^[\W_]*{re.escape(label)}\s*$", re.I)
    return first_visible(
        page.get_by_role("tab", name=name),
        page.get_by_role("tablist").get_by_role("link", name=name),
        page.locator('a[href^="#"]').filter(has_text=name),
        page.get_by_role("link", name=name),
        page.get_by_role("button", name=name),
        legacy_fallback(page, "tab", tab=key),
    )


def open_tab(state: State, tab: str) -> None:
    """
    Show a tab of an edit page, the way a person does. A tab that is a link
    to a page of its own goes direct when it is out of sight; a tab that
    cannot be found at all is a warning, and the step goes on, since a later
    move may still find what the tab holds.
    """
    page = state.page
    link = find_tab(state, tab)
    if link is not None:
        target = link.get_attribute("aria-controls") or (
            (link.get_attribute("href") or "")[1:]
            if (link.get_attribute("href") or "").startswith("#")
            else ""
        )
        click(state, link)
        if target:
            # A tab is shown a moment after it is pressed; what it names by
            # its link or its aria-controls is waited for, if it is there.
            try:
                page.wait_for_function(
                    "id => { const el = document.getElementById(id);"
                    " return el !== null && el.getClientRects().length > 0 }",
                    arg=target,
                    timeout=VISIBLE_MS,
                )
            except PlaywrightTimeout:
                logger.debug("%s did not show on %s", target, page.url)
        return
    label = TAB_LABELS.get(tab, tab)
    name = re.compile(rf"^[\W_]*{re.escape(label)}\s*$", re.I)
    hidden = page.get_by_role("link", name=name, include_hidden=True)
    for candidate in each(hidden):
        href = candidate.get_attribute("href") or ""
        if href and not href.startswith("#") and not href.startswith("javascript"):
            go_direct(
                state, href, f"no visible tab called {label!r} (a link to {href})"
            )
            return
    state.notes.append(f"the {label!r} tab was not found")
    state.warnings.append(
        f"could not open the {label!r} pane: no tab, tablist link, anchor link or "
        "link of that name"
    )


def pick_add(links: Locator) -> Locator:
    """Of several links to the same place, the one that says it adds."""
    for link in each(links):
        said = " ".join(
            filter(
                None,
                [
                    link.text_content(),
                    link.get_attribute("title"),
                    link.get_attribute("aria-label"),
                ],
            )
        )
        if ADD_WORDS.search(said):
            return link
    return links.first


def follow(state: State, suffix: str, reason: str, *, to: str | None = None) -> None:
    """
    Follow the link on the page whose address ends in ``suffix``; when more
    than one is on show, the one whose text says add, new or create. When the
    page has none to follow the step goes to ``to`` (or to the address of a
    link that is there but hidden) and says ``reason``.
    """
    page = state.page
    visible = page.locator(f"a[href$={quoted(suffix)}]").filter(visible=True)
    if visible.count():
        click(state, pick_add(visible))
        return
    if to is None:
        hidden = page.locator(f"a[href$={quoted(suffix)}]")
        if not hidden.count():
            raise AssertionError(f"no link to {suffix} on {page.url}")
        to = hidden.first.get_attribute("href")
    go_direct(state, to, reason)


def go_direct(state: State, address: str, reason: str) -> None:
    state.direct(reason)
    state.page.goto(urljoin(state.base, address), wait_until="load")
    settle(state.page)


def open_menu(state: State, component: str, href: str) -> None:
    """
    Choose ``href`` from the entry of the main menu called ``component``. A
    folded menu is opened first, with whatever control folds it, and when the
    menu has no such entry or no such item the step goes direct.
    """
    page = state.page

    def entry() -> Locator | None:
        return first_visible(
            page.get_by_role("navigation").get_by_role(
                "link", name=component, exact=True
            ),
            page.get_by_role("link", name=component, exact=True),
            page.get_by_role("button", name=component, exact=True),
        )

    def entry_text() -> Locator | None:
        # Text alone may be a label of the page's own, so it is the last resort.
        return first_visible(
            page.get_by_role("navigation").get_by_text(component, exact=True),
            page.get_by_text(component, exact=True),
        )

    def item() -> Locator | None:
        return first_visible(
            page.get_by_role("navigation").locator(f"a[href={quoted(href)}]"),
            page.locator(f"a[href={quoted(href)}]"),
        )

    target = (
        entry() or reveal(state, entry, lambda: menu_togglers(page)) or entry_text()
    )
    if target is None:
        go_direct(
            state,
            href,
            f"no menu entry called {component!r} "
            "(looked for a link, a button and text)",
        )
        return
    click(state, target)
    found = item()
    if found is None:
        # Opening the menu on hover and then clicking can close it again.
        click(state, target)
        found = item()
    if found is None:
        go_direct(state, href, f"the {component!r} menu has no link to {href}")
        return
    click(state, found)


def open_named(state: State, name: str, url_key: str | None = None) -> None:
    """
    Open the object a list shows under ``name``. An object the flow has opened
    before can be reached by its noted address when the list does not show it.
    """
    page = state.page
    target = first_visible(
        page.get_by_role("link", name=name, exact=True),
        page.get_by_text(name, exact=True),
    )
    if target is not None:
        click(state, target)
        return
    noted = state.data.get(url_key) if url_key else None
    if noted:
        go_direct(state, noted, f"the page shows no link called {name!r}")
        return
    raise AssertionError(f"no link called {name!r} on {page.url}")


def person_label(state: State, first: str) -> str:
    """How a list prints a person the flow made: the last name first."""
    return f"{state.name('Fairwind')}, {first}"


def dialog_button(page: Page, names: re.Pattern) -> Locator | None:
    """
    The button in the dialog on show that ``names`` matches. A dialog that is
    marked hidden from the accessibility tree, as Bootstrap 3 leaves it, is
    found all the same.
    """
    dialogs = page.get_by_role("dialog", include_hidden=True).filter(visible=True)
    if not dialogs.count():
        return None
    return first_visible(
        dialogs.last.get_by_role("button", name=names, include_hidden=True),
        dialogs.last.get_by_role("link", name=names, include_hidden=True),
    )


def confirm(state: State, before: str) -> None:
    """
    Answer what the click on a delete or undo control asked. A dialog on show
    has its confirming button pressed; a page of its own (the address changed)
    has its confirming button pressed; a browser's own prompt has been
    accepted already, and nothing is left to do.
    """
    page = state.page
    deadline = time.monotonic() + DIALOG_WAIT_S
    while True:
        button = dialog_button(page, CONFIRM_NAMES)
        if button is None and page.url != before:
            button = first_visible(page.get_by_role("button", name=CONFIRM_NAMES))
        if button is not None or time.monotonic() > deadline:
            break
        page.wait_for_timeout(100)
    if button is not None:
        click(state, button)
    else:
        settle(page)


def expect_visible(locator: Locator, what: str) -> None:
    """Raise unless ``locator`` shows something."""
    if not locator.filter(visible=True).count():
        raise AssertionError(f"{what} is not shown")


# --------------------------------------------------------------------------
# Finding the way back to what an earlier step made.


def at(state: State, key: str) -> bool:
    """Whether the page is the one the flow noted down as ``key``."""
    return path_of(state.page.url) == state.data.get(key)


def open_competition(state: State) -> None:
    """The competition the flow made, from wherever the flow is."""
    if at(state, "competition_url"):
        return
    open_menu(state, "Tournament Control", COMPETITIONS)
    open_named(state, state.data["competition"], "competition_url")


def open_season(state: State) -> None:
    if at(state, "season_url"):
        return
    open_competition(state)
    open_tab(state, "seasons")
    open_named(state, state.data["season"], "season_url")


def open_division(state: State, key: str = "division") -> None:
    if at(state, key + "_url"):
        return
    open_season(state)
    open_tab(state, "divisions")
    open_named(state, state.data[key], key + "_url")


# --------------------------------------------------------------------------
# The thirteen steps.


def step_1_sign_in(page: Page, state: State) -> str:
    page.goto(state.base + LOGIN_PATH, wait_until="load", timeout=NAVIGATION_MS)
    state.notes.append("entered the site at its sign-in address")
    type_into(state, "username", USERNAME)
    type_into(state, "password", PASSWORD)
    click(state, page.get_by_role("button", name="Sign in"))
    if path_of(page.url).startswith(LOGIN_PATH):
        raise AssertionError(f"signing in as {USERNAME} left the page at {page.url}")
    return state.via


def step_2_competition(page: Page, state: State) -> str:
    title = state.data["competition"] = state.name("Flow Cup")
    open_menu(state, "Tournament Control", COMPETITIONS)
    follow(state, "/competition/add/", "the list has no link to add a competition")
    type_into(state, "title", title)
    type_into(state, "short_title", "Flow")
    save(state)
    see(state, title)

    open_named(state, title)
    state.data["competition_url"] = path_of(page.url)

    club_role = state.data["club_role"] = state.name("Delegate")
    open_tab(state, "club_roles")
    follow(state, "/role-club/add/", "the Club roles tab has no link to add a role")
    type_into(state, "name", club_role)
    save(state)
    see(state, club_role, "club_roles")

    team_role = state.data["team_role"] = state.name("Manager")
    open_tab(state, "team_roles")
    follow(state, "/role-team/add/", "the Team roles tab has no link to add a role")
    type_into(state, "name", team_role)
    save(state)
    see(state, team_role, "team_roles")
    return state.via


def step_3_season(page: Page, state: State) -> str:
    title = state.data["season"] = state.name("Flow Season")
    start = state.date(7)
    open_competition(state)
    open_tab(state, "seasons")
    follow(state, "/seasons/add/", "the Seasons tab has no link to add a season")
    type_into(state, "title", title)
    type_date(state, "start_date", start)
    save(state)
    see(state, title, "seasons")
    open_named(state, title)
    state.data["season_url"] = path_of(page.url)

    open_tab(state, "exclusions")
    for days in (14, 21):
        follow(
            state, "/exclusion/add/", "the Exclusion dates tab has no link to add one"
        )
        type_date(state, "date", state.date(days))
        save(state)
        see(state, date_pattern(state.date(days)), "exclusions")

    open_tab(state, "timeslots")
    follow(state, "/timeslot/add/", "the Time slots tab has no link to add one")
    type_into(state, "start", "18:00")
    type_into(state, "interval", "45")
    type_into(state, "count", "2")
    save(state)
    see(state, time_pattern(datetime.time(18, 0)), "timeslots")

    venue = state.data["venue"] = state.name("Flow Park")
    open_tab(state, "venues")
    follow(state, "/venue/add/", "the Venues tab has no link to add a venue")
    type_into(state, "title", venue)
    choose(state, "timezone", "Australia/Sydney")
    # The map is edited by hand: its coordinates are fields that are read only
    # until an Edit button is pressed, when the form has such a button.
    if first_visible(page.locator('[name="latlng_0"]:not([readonly])')) is None:
        edit = first_visible(page.get_by_role("button", name="Edit", exact=True))
        if edit is not None:
            click(state, edit, nav=False)
    for n, value in enumerate(VENUE_PLACE):
        type_into(state, f"latlng_{n}", value)
    save(state)
    see(state, venue, "venues")
    open_named(state, venue)
    open_tab(state, "grounds")
    for letter in ("A", "B"):
        ground = state.name(f"Field {letter}")
        follow(state, "/ground/add/", "the Grounds tab has no link to add a ground")
        type_into(state, "title", ground)
        save(state)
        see(state, ground, "grounds")
    return state.via


def step_4_clubs_and_people(page: Page, state: State) -> str:
    people = []
    for key, club_name, first in (
        ("club_a", "Flow Harriers", "Ottoline"),
        ("club_b", "Flow Mariners", "Peregrine"),
    ):
        club = state.data[key] = state.name(club_name)
        open_menu(state, "Tournament Control", CLUBS)
        follow(state, "/club/add/", "the list has no link to add a club")
        type_into(state, "title", club)
        type_into(state, "slug", club.lower().replace(" ", "-"))
        save(state)
        see(state, club)

        open_named(state, club)
        state.data[key + "_url"] = path_of(page.url)
        open_tab(state, "members")
        follow(state, "/person/add/", "the People tab has no link to add a person")
        type_into(state, "first_name", first)
        type_into(state, "last_name", state.name("Fairwind"))
        choose(state, "gender", "Female")
        save(state)
        label = person_label(state, first)
        see(state, label, "members")
        people.append(label)
    state.data["person_a"], state.data["person_b"] = people

    # A competition offers its teams the clubs it has taken in.
    open_competition(state)
    for key in ("club_a", "club_b"):
        choose(state, "clubs", state.data[key])
    save(state)
    see(state, state.data["competition"])

    # Today's admin cannot give a person a role in a club: no page links to
    # the form, and saving it fails with an IntegrityError (the club is not set
    # on a new club association). The flow leaves it alone and says so.
    state.skip(
        "a person's role in a club (club association): no page links to its form "
        "and saving it fails with an IntegrityError (club_id is null)"
    )

    open_season(state)
    open_tab(state, "referees")
    follow(state, "/referees/add/", "the Referees tab has no link to add a referee")
    choose(state, "person", people[1])
    choose(state, "club", state.data["club_b"])
    save(state)
    see(state, people[1], "referees")
    return state.via


def step_5_divisions_and_teams(page: Page, state: State) -> str:
    divisions = [state.name("Flow Open"), state.name("Flow Youth")]
    state.data["division"], state.data["division_two"] = divisions
    open_season(state)
    open_tab(state, "divisions")
    bulk_create(state, "Add several divisions", len(divisions), "division")
    for n, title in enumerate(divisions):
        type_into(state, f"form-{n}-title", title)
        type_into(state, f"form-{n}-forfeit_for_score", "5")
        type_into(state, f"form-{n}-forfeit_against_score", "0")
    save(state)
    for title in divisions:
        see(state, title, "divisions")

    open_named(state, divisions[0])
    state.data["division_url"] = path_of(page.url)
    state.workaround(
        "a division made with the bulk form has no points formula, and saving a "
        "result for it fails with a 500 (calc.parse(None)); one is set first"
    )
    for n, points in enumerate(("3", "2", "1")):
        type_into(state, f"points_formula_{n}", points)
    save(state)
    see(state, divisions[0], "divisions")
    open_division(state)
    open_tab(state, "teams")
    names = [
        state.name(n)
        for n in ("Flow Hawks", "Flow Herons", "Flow Otters", "Flow Gulls")
    ]
    state.data["teams"] = names
    bulk_create(state, "Add several teams", len(names), "team")
    clubs = [state.data["club_a"]] * 2 + [state.data["club_b"]] * 2
    for n, (title, club) in enumerate(zip(names, clubs)):
        choose(state, f"form-{n}-club", club)
        type_into(state, f"form-{n}-title", title)
    save(state)
    for title in names:
        see(state, title, "teams")

    open_named(state, names[0])
    open_tab(state, "people")
    follow(state, "/association/add/", "the Linked people tab has no link to add one")
    choose(state, "person", state.data["person_a"])
    save(state)
    see(state, state.data["person_a"], "people")
    return state.via


def bulk_create(state: State, title: str, count: int, segment: str) -> None:
    """
    Open the bulk create page of a tab, through the control that asks how many
    to add. A tab with no such control goes direct to the bulk address, which
    is the address of its add link with ``bulk/`` in place of ``add/``.
    """
    page = state.page
    opener = first_visible(
        page.get_by_role("button", name=title),
        page.get_by_role("link", name=title),
        page.get_by_title(title),
    )
    if opener is not None:
        click(state, opener, nav=False)
        box = first_visible(
            page.get_by_label(re.compile("how many", re.I)),
            page.get_by_role("spinbutton"),
        )
        if box is not None:
            aim(state, box).fill(str(count))
            go = dialog_button(page, CONTINUE_NAMES) or first_visible(
                page.get_by_role("button", name=CONTINUE_NAMES)
            )
            if go is not None:
                click(state, go)
                return
    add = page.locator(f"a[href$={quoted(f'/{segment}/add/')}]")
    if not add.count():
        raise AssertionError(
            f"no control called {title!r} and no link to add a {segment} on {page.url}"
        )
    bulk = add.first.get_attribute("href")[: -len("add/")] + "bulk/"
    go_direct(state, f"{bulk}?count={count}", f"no way to ask for several: {title}")


def step_6_draw(page: Page, state: State) -> str:
    # The seeded round robins are for three, six and eight teams, and four teams
    # asks for a round robin of four, so the format is made first.
    format_name = state.data["format"] = state.name("Flow round robin")
    open_menu(state, "Tournament Control", DRAW_FORMATS)
    follow(state, "/draw-format/add/", "the list has no link to add a draw format")
    type_into(state, "name", format_name)
    type_into(state, "text", ROUND_ROBIN_FOUR, force=True)
    type_into(state, "teams", "4")
    save(state)
    see(state, format_name)

    stage = state.data["stage"] = state.name("Flow Regular Season")
    open_division(state)
    open_tab(state, "stages")
    follow(state, "/stage/add/", "the Stages tab has no link to add a stage")
    type_into(state, "title", stage)
    save(state)
    see(state, stage)
    # A new stage opens on its own page; Cancel goes back to the division.
    cancel(state)
    open_tab(state, "stages")

    # The wizard asks for a format and a start date, then shows the matches.
    follow(state, "/build/", "the stage has no Build button")
    choose(state, "0-0-format", format_name)
    save(state)
    save(state)
    see(state, stage, "stages")
    expect_visible(
        page.get_by_role("row")
        .filter(has_text=stage)
        .get_by_role("button", name=UNDO_NAMES),
        "the Undo button of the drawn stage",
    )

    # The finals follow on in a second stage, with a place waiting for a
    # team. Today's admin offers no way to place teams in
    # a pool, so the pool is added to the finals stage and left empty.
    finals = state.data["finals"] = state.name("Flow Finals")
    follow(state, "/stage/add/", "the Stages tab has no link to add a stage")
    type_into(state, "title", finals)
    save(state)
    see(state, finals)

    pool = state.name("Flow Pool")
    open_tab(state, "pools")
    follow(state, "/pool/add/", "the Pools tab has no link to add a pool")
    type_into(state, "title", pool)
    save(state)
    see(state, pool)
    state.skip(
        "placing teams in a pool: no page offers it (the team form has no pool), "
        "so the pool is on the finals stage and the regular stage is drawn without pools"
    )
    cancel(state)

    # A place with no formula is filled by hand when the stage is progressed,
    # and shows the label it is given (with a formula the label is not kept).
    label = state.data["undecided"] = state.name("Minor premiers")
    open_tab(state, "undecided_teams")
    follow(state, "/team/add/", "the Undecided teams tab has no link to add one")
    type_into(state, "label", label)
    save(state)
    see(state, label, "undecided_teams")
    return state.via


def match_day(state: State) -> str:
    """The first match day, as the admin writes it in an address."""
    return state.date(7).strftime("%Y%m%d")


def open_day(state: State, page_name: str) -> None:
    """Open ``page_name`` (schedule or results) for the first match day, from the season."""
    open_season(state)
    open_tab(state, "schedule")
    follow(
        state,
        f"/{match_day(state)}/{page_name}/",
        f"the Schedule tab has no link to the day's {page_name} page",
    )


ALLOCATIONS = (("Field A", "18:00"), ("Field B", "18:00"))


def step_7_schedule(page: Page, state: State) -> str:
    # The visual scheduler opens in a new tab, so the day's Allocate form is
    # used: a time and a ground for each of the day's matches.
    open_day(state, "schedule")
    for n, (ground, kick_off) in enumerate(ALLOCATIONS):
        choose(state, f"form-{n}-time", kick_off)
        choose(state, f"form-{n}-play_at", state.name(ground))
    save(state)
    see(state, "saved")
    # What was saved is read back from the form it came from.
    open_day(state, "schedule")
    for n, (ground, kick_off) in enumerate(ALLOCATIONS):
        kept_time = page.locator(f'select[name="form-{n}-time"]').evaluate(
            SELECTED_TEXT_SCRIPT
        )
        kept_ground = page.locator(f'select[name="form-{n}-play_at"]').evaluate(
            SELECTED_TEXT_SCRIPT
        )
        if kick_off not in kept_time:
            raise AssertionError(f"form-{n}-time kept {kept_time!r}")
        if state.name(ground) not in kept_ground:
            raise AssertionError(f"form-{n}-play_at kept {kept_ground!r}")
    return state.via


def step_8_results(page: Page, state: State) -> str:
    open_day(state, "results")
    scores = ((7, 3), (4, 6))
    for n, (home, away) in enumerate(scores):
        type_into(state, f"matches-{n}-home_team_score", str(home))
        type_into(state, f"matches-{n}-away_team_score", str(away))
    save(state)
    see(state, "saved")
    # The division page carries no ladder today, so the saved scores are
    # checked where they were entered.
    state.skip(
        "the ladder on the division page: the page has no ladder, so the saved "
        "scores are checked on the Results page"
    )
    open_day(state, "results")
    for n, (home, away) in enumerate(scores):
        for name, score in (("home", home), ("away", away)):
            field_name = f"matches-{n}-{name}_team_score"
            if page.locator(f"[name={quoted(field_name)}]").input_value() != str(score):
                raise AssertionError(f"{field_name} did not keep {score}")
    return state.via


def step_9_undo_draw(page: Page, state: State) -> str:
    open_division(state)
    open_tab(state, "stages")
    row = page.get_by_role("row").filter(has_text=state.data["stage"])
    undo = first_visible(
        row.get_by_role("button", name=UNDO_NAMES),
        row.get_by_role("link", name=UNDO_NAMES),
        legacy_fallback(row, "row_undo"),
    )
    if undo is None:
        raise AssertionError("the stage's row has no control to undo the draw")
    before = page.url
    click(state, undo)
    confirm(state, before)
    see(state, state.data["stage"], "stages")
    if not row.locator('a[href$="/build/"]').count():
        raise AssertionError("the stage can not be built again after the undo")
    return state.via


def step_10_content(page: Page, state: State) -> str:
    category = state.name("Flow Club news")
    open_menu(state, "News", NEWS_CATEGORIES)
    follow(state, "/category/add/", "the list has no link to add a category")
    type_into(state, "title", category)
    save(state)
    see(state, category)

    headline = state.name("Flow Cup begins")
    open_menu(state, "News", NEWS_ARTICLES)
    follow(state, "/article/add/", "the list has no link to add an article")
    type_into(state, "headline", headline)
    attach(state, "image", photo(headline, (1200, 800)))
    type_into(state, "abstract", state.name("Flow Cup opens this week"), force=True)
    type_date(state, "published", state.date(0), datetime.time(9, 0))
    choose(state, "categories", category)
    save(state)
    see(state, headline)
    open_named(state, headline)
    open_tab(state, "translations")
    follow(state, "/add/", "the Translations tab has no link to add one")
    translated = state.name("La Flow Cup commence")
    choose(state, "locale", "French")
    type_into(state, "headline", translated)
    type_into(state, "abstract", state.name("La Flow Cup ouvre"), force=True)
    save(state)
    # The list names the language; the headline is read back from the
    # translation's own page. A save that did nothing would leave the add
    # form on show, with "French" in it, so the list is looked for by its link.
    open_tab(state, "translations")
    expect_visible(
        page.get_by_role("link", name="French", exact=True), "the French translation"
    )
    open_named(state, "French")
    see(state, translated)

    label = state.name("Flow old fixtures")
    open_menu(state, "Content", REDIRECTS)
    follow(state, "/redirect/create/", "the list has no link to add a redirect")
    type_into(state, "source_url", f"/flow-old-fixtures-{state.stamp}/")
    type_into(state, "destination_url", "/")
    type_into(state, "label", label)
    save(state)
    see(state, label)

    about = state.name("Flow About")
    open_menu(state, "Content", SITEMAP)
    follow(state, "/page/add/", "the sitemap has no link to add a page")
    type_into(state, "parent-form-title", about)
    save(state)
    see(state, about)
    return state.via


def step_11_enrolment(page: Page, state: State) -> str:
    # A school year's title is four characters and unique, a class's is ten:
    # the year is derived from the stamp and the class is the stamp.
    year = state.data["year"] = state.year
    grade = state.data["grade"] = state.name("Flow Grade")
    teacher_last = state.name("Marlowe")
    class_group = state.data["class"] = state.name("Fc")
    # The lists print a class with its year, and an enrolment with the class.
    class_label = state.data["class_label"] = f"{class_group} ({year})"

    open_menu(state, "Enrolment", ENROLMENT_YEARS)
    follow(state, "/year/add/", "the list has no link to add a school year")
    type_into(state, "title", year)
    type_date(state, "start_date", state.date(0))
    type_date(state, "end_date", state.date(300))
    save(state)
    see(state, year)

    open_menu(state, "Enrolment", ENROLMENT_GRADES)
    follow(state, "/grade/add/", "the list has no link to add a grade")
    type_into(state, "title", grade)
    type_into(state, "ordinal", str(1000 + int(state.stamp[-4:])))
    save(state)
    see(state, grade)

    open_menu(state, "Enrolment", ENROLMENT_TEACHERS)
    follow(state, "/teacher/add/", "the list has no link to add a teacher")
    type_into(state, "first_name", "Odette")
    type_into(state, "last_name", teacher_last)
    type_into(state, "email", "odette.marlowe@example.org")
    save(state)
    see(state, teacher_last)

    open_menu(state, "Enrolment", ENROLMENT_YEARS)
    open_named(state, year)
    state.data["year_url"] = path_of(page.url)
    open_tab(state, "classes")
    follow(state, "/class/add/", "the Class groups tab has no link to add a class")
    choose(state, "grade", grade)
    type_into(state, "title", class_group)
    choose(state, "teacher", teacher_last)
    save(state)
    see(state, class_label, "classes")

    students = []
    open_menu(state, "Enrolment", ENROLMENT_STUDENTS)
    for first in ("Ptolemy", "Rosalind"):
        last = state.name("Quillfeather")
        follow(state, "/student/add/", "the list has no link to add a student")
        type_into(state, "first_name", first)
        type_into(state, "last_name", last)
        type_date(state, "date_of_birth", datetime.date(2016, 5, 4))
        type_into(state, "guardian_name", "A. Guardian")
        type_into(state, "guardian_phone", GUARDIAN_PHONE)
        save(state)
        # The list is long and the new student is not on its first page.
        search(state, last)
        see(state, last)
        students.append(f"{first} {last}")
    state.data["students"] = students

    open_class(state)
    open_tab(state, "enrolments")
    for student in students:
        follow(
            state,
            "/enrolment/add/",
            "the Enrolments tab has no link to enrol a student",
        )
        choose(state, "student", student)
        save(state)
        see(state, f"{student} in {class_label}", "enrolments")

    open_named(state, f"{students[0]} in {class_label}", "enrolment_url")
    state.data["enrolment_url"] = path_of(page.url)
    open_tab(state, "attendance")
    follow(state, "/attendance/add/", "the Attendance tab has no link to add a record")
    type_date(state, "date", state.date(0))
    save(state)
    see(state, attendance_record(state), "attendance")

    open_class(state)
    open_tab(state, "assessments")
    follow(state, "/assessment/add/", "the Assessments tab has no link to add one")
    assessment = state.name("Flow Reading")
    type_into(state, "title", assessment)
    type_date(state, "date", state.date(0))
    type_into(state, "maximum_mark", "20")
    save(state)
    see(state, assessment, "assessments")
    marks = (16, 18)
    for student, mark in zip(students, marks):
        open_named(state, assessment)
        choose(state, f"formset-{scored(state)}-enrolment", student)
        type_into(state, f"formset-{scored(state)}-mark", str(mark))
        save(state)
        state.data["scores"] = scored(state) + 1
    # Every mark entered is on the assessment when it is opened again.
    open_named(state, assessment)
    kept = page.locator('input[name$="-mark"]').evaluate_all(
        "fields => fields.map(f => f.value)"
    )
    for mark in marks:
        if not any(value.split(".")[0] == str(mark) for value in kept):
            raise AssertionError(
                f"the mark {mark} was not kept (the form shows {kept})"
            )

    open_enrolment(state)
    open_tab(state, "report_cards")
    follow(state, "/report/add/", "the Report cards tab has no link to add one")
    choose(state, "term", "Term 1")
    type_into(
        state, "literacy", state.name("Reads with growing confidence"), force=True
    )
    type_into(state, "general_comment", state.name("A good start"), force=True)
    save(state)
    see(state, "Term 1", "report_cards")
    return state.via


def scored(state: State) -> int:
    """How many scores of the flow's assessment are saved, which is the next form."""
    return state.data.get("scores", 0)


def attendance_record(state: State) -> str:
    """How a list prints the attendance record the flow made."""
    return f"{state.date(0).isoformat()}: present"


def open_class(state: State) -> None:
    """The class the flow made, from wherever the flow is."""
    if at(state, "class_url"):
        return
    open_menu(state, "Enrolment", ENROLMENT_YEARS)
    open_named(state, state.data["year"], "year_url")
    open_tab(state, "classes")
    open_named(state, state.data["class_label"])
    state.data["class_url"] = path_of(state.page.url)


def open_enrolment(state: State) -> None:
    if not at(state, "enrolment_url"):
        open_class(state)
        open_tab(state, "enrolments")
        open_named(
            state,
            f"{state.data['students'][0]} in {state.data['class_label']}",
            "enrolment_url",
        )


def step_12_delete_attendance(page: Page, state: State) -> str:
    open_enrolment(state)
    open_tab(state, "attendance")
    record = attendance_record(state)
    row = page.get_by_role("row").filter(has_text=record)

    def delete() -> Locator | None:
        return first_visible(
            row.get_by_role("button", name=DELETE_NAMES),
            row.get_by_role("link", name=DELETE_NAMES),
        )

    # The row's actions are folded into a menu of their own.
    target = delete() or reveal(
        state,
        delete,
        lambda: [
            *each(row.get_by_role("button", name=ROW_MENU_NAMES).filter(visible=True)),
            *each(row.locator("button[aria-expanded]").filter(visible=True)),
            *each(legacy_fallback(row, "row_menu").filter(visible=True)),
        ],
    )
    if target is None:
        raise AssertionError("the attendance record's row has no control to delete it")
    before = page.url
    click(state, target)
    confirm(state, before)
    if not at(state, "enrolment_url"):
        raise AssertionError(f"the delete went to {page.url}, not the enrolment")
    open_tab(state, "attendance")
    if page.get_by_text(record).filter(visible=True).count():
        raise AssertionError("the attendance record is still listed")
    return state.via


def step_13_sign_out(page: Page, state: State) -> str:
    def logout() -> Locator | None:
        return first_visible(
            page.get_by_role("button", name=LOGOUT_NAMES),
            page.get_by_role("link", name=LOGOUT_NAMES),
            page.get_by_text(LOGOUT_NAMES),
        )

    target = logout() or reveal(state, logout, lambda: profile_togglers(page))
    if target is not None:
        click(state, target)
    else:
        sign_out_direct(state)
    if not path_of(page.url).startswith(LOGIN_PATH):
        raise AssertionError(f"signing out left the page at {page.url}")
    page.get_by_role("button", name="Sign in").wait_for(
        state="visible", timeout=VISIBLE_MS
    )
    return state.via


def sign_out_direct(state: State) -> None:
    """
    Sign out with a request, for an admin that offers no control for it. The
    sign-out address takes a POST, and the page's own form is the model for
    it: the token comes from the cookie the admin set.
    """
    page = state.page
    action = page.locator('form[action$="/logout/"]')
    address = action.first.get_attribute("action") if action.count() else LOGOUT_PATH
    token = next(
        (c["value"] for c in page.context.cookies() if c["name"] == "csrftoken"), ""
    )
    page.request.post(
        urljoin(state.base, address),
        form={"csrfmiddlewaretoken": token},
        headers={"Referer": state.base + "/admin/"},
    )
    state.direct(
        "no control for signing out was found (looked for a button or link called Logout, Log out or Sign out)"
    )
    page.goto(state.base + LOGIN_PATH, wait_until="load")
    settle(page)


STEPS = [
    step_1_sign_in,
    step_2_competition,
    step_3_season,
    step_4_clubs_and_people,
    step_5_divisions_and_teams,
    step_6_draw,
    step_7_schedule,
    step_8_results,
    step_9_undo_draw,
    step_10_content,
    step_11_enrolment,
    step_12_delete_attendance,
    step_13_sign_out,
]


# --------------------------------------------------------------------------
# The driver.


def failed_shot(page: Page, width: int) -> str:
    """A picture of the page a step failed on, beside the video."""
    try:
        directory = Path(page.video.path()).parent
        name = f"flow-{width}-failed.png"
        page.screenshot(path=str(directory / name))
        return name
    except (PlaywrightError, OSError, AttributeError):
        return ""


def known_page_error(message: str) -> str | None:
    """Why the collector's ``message`` is allowed, when it is one of the known ones."""
    if message.startswith(PAGE_ERROR_PREFIX):
        return KNOWN_PAGE_ERRORS.get(message[len(PAGE_ERROR_PREFIX) :])
    return None


def run(
    page: Page,
    base: str,
    manifest: Manifest,
    width: int,
    collector,
    checkpoint: Callable[[], None] | None = None,
) -> None:
    """
    Run every step in ``page`` and add a ``StepResult`` for each to
    ``manifest.flow``. ``collector`` is what listens to ``page``. The stamp of
    the run is noted in ``manifest.flow_stamps`` before the first step, so
    that ``python -m harness unflow`` can remove what the run made however it
    ends; ``checkpoint`` is called after every change to the manifest.

    What the page raises while a step runs fails the step: an uncaught page
    error (but for the exact ones in ``KNOWN_PAGE_ERRORS``), a console error
    and a failed request to the server under test. A step that raised is the
    last; one that only met such an error lets the flow go on, so that the
    recording reaches its end.
    """
    now = datetime.datetime.now()
    state = State(
        page=page,
        base=base.rstrip("/"),
        width=width,
        stamp=now.strftime("%H%M%S"),
        today=now.date(),
    )
    manifest.flow_stamps[str(width)] = state.stamp
    # A browser's own confirmation prompt is answered yes, as a person would.
    page.on("dialog", lambda dialog: dialog.accept())
    if checkpoint:
        checkpoint()
    for step in STEPS:
        name = step.__name__
        state.begin()
        collector.drain()
        started = time.monotonic()
        errors: list[str] = []
        file = ""
        crashed = False
        returned = None
        try:
            returned = step(page, state)
        except Exception as exc:  # noqa: BLE001 - every failure is recorded
            crashed = True
            summary = " ".join(str(exc).split("\n", 4)[:4])
            errors.append(f"{type(exc).__name__}: {summary}")
            file = failed_shot(page, width)
        if not crashed and returned != state.via:
            errors.append(
                f"the step reported {returned!r} but its moves needed {state.via!r}"
            )
        raised, warnings = collector.drain()
        for message in raised:
            known = known_page_error(message)
            if known:
                warnings.append(f"{known} ({message})")
            else:
                errors.append(message)
        result = StepResult(
            name=name,
            width=width,
            url=urlparse(page.url).path,
            via=state.via,
            note="; ".join(state.notes),
            status="failed" if errors else "ok",
            duration=round(time.monotonic() - started, 1),
            errors=errors,
            warnings=state.warnings + warnings,
            file=file,
        )
        manifest.flow.append(result)
        if checkpoint:
            checkpoint()
        failed = " FAILED" if errors else ""
        print(
            f"flow {width} {name} {result.via}{failed} ({result.duration:.1f} s)",
            flush=True,
        )
        for message in errors:
            print(f"    error: {message}", flush=True)
        if crashed:
            break
