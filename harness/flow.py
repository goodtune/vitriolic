"""An administrator's errand through the whole admin, for the video.

The flow signs in and then builds a small competition from nothing, running
it through a draw, a schedule and results, adds news and pages, runs a school
enrolment and signs out. Each of the thirteen ``step_<n>_<name>`` functions is
one stretch of that errand and returns how it got where it was going:

``"link"``    every move followed a link, button or menu the page offered;
``"scroll"``  the same, but a target had to be scrolled into view first;
``"direct"``  the address was typed, because today's admin offers no link.

A step that went direct says why in its ``note`` and records a warning, which
is evidence about the admin and not a failure. An uncaught page error, a step
that raises, or a saved title that is not on the page it returned to does fail
the flow, and the run with it.

Everything the flow creates has an invented name ending in the run stamp, so
repeated runs, and the page captures that follow them, never collide. Elements
are found by role, accessible name, URL (``a[href="..."]``) or form field
name, never by CSS class. A headless recording shows no pointer, so the target
of every click is ringed for a moment first.
"""

import datetime
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from harness.images import photo
from harness.manifest import Manifest, StepResult

logger = logging.getLogger(__name__)

LOGIN_PATH = "/admin/login/"
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

#: Page errors the baseline admin raises that the flow must pass through. Each
#: is recorded as a warning on the step that met it instead of failing the
#: flow, so that a recording of the baseline still reaches the end. Anything
#: else uncaught fails the flow.
KNOWN_PAGE_ERRORS = {
    "_DT_CellIndex": (
        "known baseline error: the club edit page runs DataTables on every "
        "table, and DataTables 1.10 cannot take the colspan cell of an empty "
        "list (club/edit.html prepareTables, mvp/list.inc.html table-row-empty)"
    ),
}

#: A round robin of four teams, in the draw format syntax.
ROUND_ROBIN_FOUR = (
    "ROUND\n1: 1 vs 4\n2: 2 vs 3\n"
    "ROUND\n3: 1 vs 3\n4: 4 vs 2\n"
    "ROUND\n5: 1 vs 2\n6: 3 vs 4"
)

#: Rank of the ways a step can reach a page; the worst one is the step's.
RANK = {"link": 0, "scroll": 1, "direct": 2}

#: The months as the admin prints them in a list (Django's "N j, Y").
MONTHS = (
    "Jan.",
    "Feb.",
    "March",
    "April",
    "May",
    "June",
    "July",
    "Aug.",
    "Sept.",
    "Oct.",
    "Nov.",
    "Dec.",
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
        self.warnings.append("went direct: %s" % reason)

    def skip(self, reason: str) -> None:
        """Record something the errand cannot do in today's admin."""
        self.notes.append("not exercised: %s" % reason)
        self.warnings.append("not exercised: %s" % reason)

    def workaround(self, reason: str) -> None:
        """Record a fault of today's admin that the errand steps around."""
        self.notes.append("workaround: %s" % reason)
        self.warnings.append("workaround: %s" % reason)

    def name(self, text: str) -> str:
        """An invented name for an object: ``text`` and the run stamp."""
        return "%s %s" % (text, self.stamp)

    def date(self, days: int) -> datetime.date:
        return self.today + datetime.timedelta(days=days)


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


def aim(state: State, target: Locator) -> Locator:
    """
    Bring ``target`` into view, ring it and hold still for a moment. Having to
    scroll is recorded, since a person has to do it too.
    """
    target = target.filter(visible=True).first
    target.wait_for(state="visible", timeout=VISIBLE_MS)
    if not target.evaluate(IN_VIEW_SCRIPT):
        state.reach("scroll")
        target.scroll_into_view_if_needed()
    target.evaluate(RING_SCRIPT)
    state.page.wait_for_timeout(PAUSE_MS)
    return target


def click(state: State, target: Locator) -> None:
    aim(state, target).click()
    settle(state.page)


def type_into(state: State, name: str, text: str, force: bool = False) -> None:
    """Type ``text`` into the visible field called ``name``."""
    target = state.page.locator('[name="%s"]:visible' % name).first
    aim(state, target)
    target.fill("")
    if len(text) <= 60 and not force:
        target.press_sequentially(text, delay=TYPING_DELAY_MS)
    else:
        target.fill(text)


def attach(state: State, name: str, picture) -> None:
    """Give the file field called ``name`` a picture (a Django ``ContentFile``)."""
    target = state.page.locator('input[type="file"][name="%s"]' % name)
    aim(state, target)
    target.set_input_files(
        {
            "name": picture.name,
            "mimeType": "image/jpeg",
            "buffer": picture.read(),
        }
    )
    state.page.wait_for_timeout(PAUSE_MS)


def choose(state: State, name: str, text: str) -> None:
    """
    Pick the option of the field called ``name`` that shows ``text``, through
    the search box of the field when the admin has dressed it as one.
    """
    page = state.page
    native = page.locator('select[name="%s"]' % name).first
    if native.is_visible():
        aim(state, native)
        label = native.locator("option", has_text=text).first.text_content()
        native.select_option(label=label)
        return
    field_id = native.get_attribute("id")
    container = page.locator('[id="s2id_%s"]' % field_id)
    # A multiple choice is opened from its search box; the first link in it
    # would be the cross that removes a choice already made.
    multiple = native.get_attribute("multiple") is not None
    opener = container.locator("input" if multiple else "a").first
    aim(state, container)
    opener.click()
    page.keyboard.type(text, delay=TYPING_DELAY_MS)
    page.wait_for_timeout(PAUSE_MS)
    page.keyboard.press("Enter")
    page.wait_for_timeout(PAUSE_MS)


def search(state: State, text: str) -> None:
    """Look ``text`` up with the search box of a long list."""
    if not state.page.locator('[name="search"]:visible').count():
        # At a phone's width the search box is folded away with the menu.
        click(state, state.page.locator('a[data-target=".mainnav-collapse"]'))
    type_into(state, "search", text)
    with state.page.expect_navigation(wait_until="load"):
        state.page.keyboard.press("Enter")
    settle(state.page)


def save(state: State) -> None:
    click(state, state.page.get_by_role("button", name="Save", exact=True))


def see(state: State, text: str, tab: str | None = None) -> None:
    """
    Check that ``text`` is on the page, as a person would look: in the page's
    text or in a field of its form. A page that comes back showing another tab
    is shown the tab the object is listed in. It raises when the text is not
    there.
    """
    page = state.page

    def shown() -> Locator:
        in_text = page.get_by_text(text).filter(visible=True)
        in_field = page.locator('input[value="%s"]' % text).filter(visible=True)
        return in_text.or_(in_field)

    if (
        tab
        and shown().count() == 0
        and page.locator('#myTab a[href="#%s-tab"]' % tab).count()
    ):
        open_tab(state, tab)
    try:
        shown().first.wait_for(state="visible", timeout=VISIBLE_MS)
        return
    except PlaywrightTimeout:
        pass
    # Lists are paged, and an object made on a database that has been used
    # before is not on the first page: turn the pages until it shows.
    pages = page.locator('a[href^="?page="]:visible').evaluate_all(
        "links => links.map(a => a.getAttribute('href'))"
    )
    for href in pages:
        click(state, page.locator('a[href="%s"]:visible' % href))
        try:
            shown().first.wait_for(state="visible", timeout=VISIBLE_MS)
            return
        except PlaywrightTimeout:
            continue
    raise AssertionError("%r is not on %s" % (text, page.url))


def open_tab(state: State, tab: str) -> None:
    """Show a tab of an edit page, the way a person does."""
    link = state.page.locator('#myTab a[href="#%s-tab"]' % tab)
    click(state, link)
    state.page.locator("#%s-tab" % tab).wait_for(state="visible", timeout=VISIBLE_MS)


def follow(state: State, suffix: str, reason: str, *, to: str | None = None):
    """
    Follow the link on the page whose address ends in ``suffix``. When the
    page has none to follow the step goes to ``to`` (or to the address of a
    link that is there but hidden) and says ``reason``.
    """
    page = state.page
    visible = page.locator('a[href$="%s"]:visible' % suffix)
    if visible.count():
        click(state, visible)
        return
    if to is None:
        hidden = page.locator('a[href$="%s"]' % suffix)
        if not hidden.count():
            raise AssertionError("no link to %s on %s" % (suffix, page.url))
        to = hidden.first.get_attribute("href")
    go_direct(state, to, reason)


def go_direct(state: State, address: str, reason: str) -> None:
    state.direct(reason)
    state.page.goto(urljoin(state.base, address), wait_until="load")
    settle(state.page)


def open_menu(state: State, component: str, href: str) -> None:
    """
    Choose ``href`` from the entry of the main menu called ``component``. At a
    phone's width the menu is folded away, so it is opened first.
    """
    page = state.page
    nav = page.get_by_role("navigation")
    entry = nav.get_by_role("link", name=component, exact=True).first
    if not entry.is_visible():
        click(state, page.locator('a[data-target=".mainnav-collapse"]'))
    click(state, entry)
    item = nav.locator('a[href="%s"]:visible' % href)
    if not item.count():
        # Opening the menu on hover and then clicking can close it again.
        click(state, entry)
    click(state, item)


def open_named(state: State, name: str) -> None:
    """Open the object a list shows under ``name``."""
    click(state, state.page.get_by_role("link", name=name, exact=True))


def ap_date(day: datetime.date) -> str:
    """A date as a list in the admin prints it, for checking a save."""
    return "%s %d, %d" % (MONTHS[day.month - 1], day.day, day.year)


def person_label(state: State, first: str) -> str:
    """How a list prints a person the flow made: the last name first."""
    return "%s, %s" % (state.name("Fairwind"), first)


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
    open_named(state, state.data["competition"])


def open_season(state: State) -> None:
    if at(state, "season_url"):
        return
    open_competition(state)
    open_tab(state, "seasons")
    open_named(state, state.data["season"])


def open_division(state: State, key: str = "division") -> None:
    if at(state, key + "_url"):
        return
    open_season(state)
    open_tab(state, "divisions")
    open_named(state, state.data[key])


# --------------------------------------------------------------------------
# The thirteen steps.


def step_1_sign_in(page: Page, state: State) -> str:
    page.goto(state.base + LOGIN_PATH, wait_until="load", timeout=NAVIGATION_MS)
    state.notes.append("entered the site at its sign-in address")
    type_into(state, "username", USERNAME)
    type_into(state, "password", PASSWORD)
    click(state, page.get_by_role("button", name="Sign in"))
    if path_of(page.url).startswith(LOGIN_PATH):
        raise AssertionError(
            "signing in as %s left the page at %s" % (USERNAME, page.url)
        )
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
    type_into(state, "start_date", start.isoformat())
    save(state)
    see(state, title, "seasons")
    open_named(state, title)
    state.data["season_url"] = path_of(page.url)

    open_tab(state, "exclusions")
    for days in (14, 21):
        follow(
            state, "/exclusion/add/", "the Exclusion dates tab has no link to add one"
        )
        type_into(state, "date", state.date(days).isoformat())
        save(state)
        see(state, ap_date(state.date(days)), "exclusions")

    open_tab(state, "timeslots")
    follow(state, "/timeslot/add/", "the Time slots tab has no link to add one")
    type_into(state, "start", "18:00")
    type_into(state, "interval", "45")
    type_into(state, "count", "2")
    save(state)
    see(state, "6 p.m.", "timeslots")

    venue = state.data["venue"] = state.name("Flow Park")
    open_tab(state, "venues")
    follow(state, "/venue/add/", "the Venues tab has no link to add a venue")
    type_into(state, "title", venue)
    choose(state, "timezone", "Australia/Sydney")
    # The map is edited by hand through its Edit button.
    click(state, page.get_by_role("button", name="Edit", exact=True))
    for n, value in enumerate(("-33.83", "151.24", "15")):
        type_into(state, "latlng_%d" % n, value)
    save(state)
    see(state, venue, "venues")
    open_named(state, venue)
    open_tab(state, "grounds")
    for letter in ("A", "B"):
        ground = state.name("Field %s" % letter)
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
    bulk_create(state, "Add several divisions", len(divisions))
    for n, title in enumerate(divisions):
        type_into(state, "form-%d-title" % n, title)
        type_into(state, "form-%d-forfeit_for_score" % n, "5")
        type_into(state, "form-%d-forfeit_against_score" % n, "0")
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
        type_into(state, "points_formula_%d" % n, points)
    save(state)
    see(state, divisions[0], "divisions")
    open_division(state)
    open_tab(state, "teams")
    names = [
        state.name(n)
        for n in ("Flow Hawks", "Flow Herons", "Flow Otters", "Flow Gulls")
    ]
    state.data["teams"] = names
    bulk_create(state, "Add several teams", len(names))
    clubs = [state.data["club_a"]] * 2 + [state.data["club_b"]] * 2
    for n, (title, club) in enumerate(zip(names, clubs)):
        choose(state, "form-%d-club" % n, club)
        type_into(state, "form-%d-title" % n, title)
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


def bulk_create(state: State, title: str, count: int) -> None:
    """Open the bulk create page of a tab, through the dialog that asks how many."""
    page = state.page
    click(state, page.get_by_title(title))
    box = page.get_by_label("How many do you want to add?")
    aim(state, box).fill(str(count))
    # The dialog is marked aria-hidden, so it is found by what it says.
    click(state, page.get_by_text("Continue", exact=True))


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
    click(state, page.get_by_role("link", name="Cancel", exact=True))
    open_tab(state, "stages")

    # The wizard asks for a format and a start date, then shows the matches.
    follow(state, "/build/", "the stage has no Build button")
    choose(state, "0-0-format", format_name)
    save(state)
    save(state)
    see(state, stage, "stages")
    see(state, "Undo", "stages")

    # The finals follow on in a second stage, with a place waiting for the
    # team that tops the ladder. Today's admin offers no way to place teams in
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
    click(state, page.get_by_role("link", name="Cancel", exact=True))

    label = state.data["undecided"] = state.name("Minor premiers")
    open_tab(state, "undecided_teams")
    follow(state, "/team/add/", "the Undecided teams tab has no link to add one")
    type_into(state, "formula", "P1")
    type_into(state, "label", label)
    save(state)
    # The list names the place the team will fill, not the label.
    see(state, "1st", "undecided_teams")
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
        "/%s/%s/" % (match_day(state), page_name),
        "the Schedule tab has no link to the day's %s page" % page_name,
    )


def step_7_schedule(page: Page, state: State) -> str:
    # The visual scheduler opens in a new tab, so the day's Allocate form is
    # used: a time and a ground for each of the day's matches.
    open_day(state, "schedule")
    for n, ground in enumerate(("Field A", "Field B")):
        choose(state, "form-%d-time" % n, "18:00")
        choose(state, "form-%d-play_at" % n, state.name(ground))
    save(state)
    see(state, "saved")
    return state.via


def step_8_results(page: Page, state: State) -> str:
    open_day(state, "results")
    scores = ((7, 3), (4, 6))
    for n, (home, away) in enumerate(scores):
        type_into(state, "matches-%d-home_team_score" % n, str(home))
        type_into(state, "matches-%d-away_team_score" % n, str(away))
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
            field_name = "matches-%d-%s_team_score" % (n, name)
            if page.locator('[name="%s"]' % field_name).input_value() != str(score):
                raise AssertionError("%s did not keep %s" % (field_name, score))
    return state.via


def step_9_undo_draw(page: Page, state: State) -> str:
    open_division(state)
    open_tab(state, "stages")
    row = page.get_by_role("row").filter(has_text=state.data["stage"])
    click(state, row.locator('a[data-action$="/undo/"]'))
    # The dialog is marked aria-hidden, so it is found by what it says.
    click(state, page.get_by_text("Undo stage", exact=True))
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
    type_into(state, "published", "%s 09:00:00" % state.date(0).isoformat())
    choose(state, "categories", category)
    save(state)
    see(state, headline)
    open_named(state, headline)
    open_tab(state, "translations")
    follow(state, "/add/", "the Translations tab has no link to add one")
    choose(state, "locale", "French")
    type_into(state, "headline", state.name("La Flow Cup commence"))
    save(state)
    see(state, "French", "translations")

    label = state.name("Flow old fixtures")
    open_menu(state, "Content", REDIRECTS)
    follow(state, "/redirect/create/", "the list has no link to add a redirect")
    type_into(state, "source_url", "/flow-old-fixtures-%s/" % state.stamp)
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
    # the year takes the last four digits of the stamp and the class the stamp.
    year = state.data["year"] = state.stamp[-4:]
    grade = state.data["grade"] = state.name("Flow Grade")
    teacher_last = state.name("Marlowe")
    class_group = state.data["class"] = state.name("Fc")
    # The lists print a class with its year, and an enrolment with the class.
    class_label = state.data["class_label"] = "%s (%s)" % (class_group, year)

    open_menu(state, "Enrolment", ENROLMENT_YEARS)
    follow(state, "/year/add/", "the list has no link to add a school year")
    type_into(state, "title", year)
    type_into(state, "start_date", state.date(0).isoformat())
    type_into(state, "end_date", state.date(300).isoformat())
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
        type_into(state, "date_of_birth", "2016-05-04")
        type_into(state, "guardian_name", "A. Guardian")
        type_into(state, "guardian_phone", "0400 000 000")
        save(state)
        # The list is long and the new student is not on its first page.
        search(state, last)
        see(state, last)
        students.append("%s %s" % (first, last))
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
        see(state, "%s in %s" % (student, class_label), "enrolments")

    open_named(state, "%s in %s" % (students[0], class_label))
    state.data["enrolment_url"] = path_of(page.url)
    open_tab(state, "attendance")
    follow(state, "/attendance/add/", "the Attendance tab has no link to add a record")
    type_into(state, "date", state.date(0).isoformat())
    save(state)
    see(state, "%s: present" % state.date(0).isoformat(), "attendance")

    open_class(state)
    open_tab(state, "assessments")
    follow(state, "/assessment/add/", "the Assessments tab has no link to add one")
    assessment = state.name("Flow Reading")
    type_into(state, "title", assessment)
    type_into(state, "date", state.date(0).isoformat())
    type_into(state, "maximum_mark", "20")
    save(state)
    see(state, assessment, "assessments")
    for student, mark in zip(students, (16, 18)):
        open_named(state, assessment)
        choose(state, "formset-%d-enrolment" % scored(state), student)
        type_into(state, "formset-%d-mark" % scored(state), str(mark))
        save(state)
        state.data["scores"] = scored(state) + 1

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


def open_class(state: State) -> None:
    """The class the flow made, from wherever the flow is."""
    if at(state, "class_url"):
        return
    open_menu(state, "Enrolment", ENROLMENT_YEARS)
    open_named(state, state.data["year"])
    open_tab(state, "classes")
    open_named(state, state.data["class_label"])
    state.data["class_url"] = path_of(state.page.url)


def open_enrolment(state: State) -> None:
    if not at(state, "enrolment_url"):
        open_class(state)
        open_tab(state, "enrolments")
        open_named(
            state, "%s in %s" % (state.data["students"][0], state.data["class_label"])
        )


def step_12_delete_attendance(page: Page, state: State) -> str:
    open_enrolment(state)
    open_tab(state, "attendance")
    record = "%s: present" % state.date(0).isoformat()
    row = page.get_by_role("row").filter(has_text=record)
    click(state, row.locator('button[data-toggle="dropdown"]'))
    click(state, row.get_by_role("button", name="Delete"))
    # The dialog names the model on its confirming button.
    click(state, page.get_by_text("Delete attendance record", exact=True))
    if not at(state, "enrolment_url"):
        raise AssertionError("the delete went to %s, not the enrolment" % page.url)
    if page.get_by_text(record).filter(visible=True).count():
        raise AssertionError("the attendance record is still listed")
    page.locator("#attendance-tab").wait_for(state="visible", timeout=VISIBLE_MS)
    return state.via


def step_13_sign_out(page: Page, state: State) -> str:
    if state.narrow:
        click(state, page.locator('button[data-target=".navbar-collapse"]'))
    click(state, page.locator('header a[data-toggle="dropdown"]'))
    click(state, page.get_by_role("button", name="Logout"))
    if not path_of(page.url).startswith(LOGIN_PATH):
        raise AssertionError("signing out left the page at %s" % page.url)
    page.get_by_role("button", name="Sign in").wait_for(
        state="visible", timeout=VISIBLE_MS
    )
    return state.via


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
        name = "flow-%d-failed.png" % width
        page.screenshot(path=str(directory / name))
        return name
    except (PlaywrightError, OSError, AttributeError):
        return ""


def run(page: Page, base: str, manifest: Manifest, width: int, collector) -> None:
    """
    Run every step in ``page`` and add a ``StepResult`` for each to
    ``manifest.flow``. ``collector`` is what listens to ``page``. The first
    step that fails ends the flow.
    """
    now = datetime.datetime.now()
    state = State(
        page=page,
        base=base.rstrip("/"),
        width=width,
        stamp=now.strftime("%H%M%S"),
        today=now.date(),
    )
    for step in STEPS:
        name = step.__name__
        state.begin()
        collector.drain()
        started = time.monotonic()
        errors: list[str] = []
        file = ""
        try:
            step(page, state)
        except Exception as exc:  # noqa: BLE001 - every failure is recorded
            errors.append(
                "%s: %s" % (type(exc).__name__, " ".join(str(exc).split("\n", 4)[:4]))
            )
            file = failed_shot(page, width)
        raised, warnings = collector.drain()
        # Only an uncaught page error fails the flow; the baseline admin logs
        # other errors (a script loaded before jQuery, a missing stylesheet).
        for message in raised:
            known = [why for part, why in KNOWN_PAGE_ERRORS.items() if part in message]
            if known:
                warnings.append("%s (%s)" % (known[0], message))
            elif message.startswith("uncaught page error"):
                errors.append(message)
            else:
                warnings.append(message)
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
        print(
            "flow %d %s %s%s (%.1f s)"
            % (width, name, result.via, " FAILED" if errors else "", result.duration),
            flush=True,
        )
        for message in errors:
            print("    error: %s" % message, flush=True)
        if errors:
            break
