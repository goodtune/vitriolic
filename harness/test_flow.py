import ast
import datetime
import re
from pathlib import Path

import pytest

from harness.flow import (
    KNOWN_PAGE_ERRORS,
    LEGACY_FALLBACKS,
    PAGE_ERROR_PREFIX,
    STEPS,
    TAB_LABELS,
    date_pattern,
    format_date,
    known_page_error,
    time_pattern,
)

EXPECTED = [
    "step_1_sign_in",
    "step_2_competition",
    "step_3_season",
    "step_4_clubs_and_people",
    "step_5_divisions_and_teams",
    "step_6_draw",
    "step_7_schedule",
    "step_8_results",
    "step_9_undo_draw",
    "step_10_content",
    "step_11_enrolment",
    "step_12_delete_attendance",
    "step_13_sign_out",
]

FLOW = Path(__file__).with_name("flow.py")


def test_the_flow_has_the_thirteen_steps_in_order():
    assert [step.__name__ for step in STEPS] == EXPECTED


def test_every_step_can_be_called():
    assert all(callable(step) for step in STEPS)


def strings_outside_the_legacy_mapping(source: str) -> list[str]:
    """Every string constant of ``source`` but docstrings and the legacy mapping."""
    tree = ast.parse(source)
    skip: set[int] = set()
    for node in ast.walk(tree):
        # Docstrings.
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
            ):
                skip.add(id(body[0].value))
        # The mapping itself.
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "LEGACY_FALLBACKS" for t in node.targets
        ):
            skip.update(id(n) for n in ast.walk(node.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
    ]


def selectors_that_name_an_id_a_class_or_data(source: str) -> list[str]:
    return [
        text
        for text in strings_outside_the_legacy_mapping(source)
        if re.match(r"\s*[#.][\w\[-]", text)
        or re.search(r"\[\s*data-", text)
        or re.search(r"\[\s*(id|class)\s*[~|^$*]?=", text)
        or re.search(r"\[(?:id|class)\b", text)
    ]


def test_no_selector_outside_the_legacy_mapping_names_an_id_a_class_or_data():
    assert selectors_that_name_an_id_a_class_or_data(FLOW.read_text()) == []


def test_the_check_finds_a_selector_that_names_an_id_a_class_or_data():
    source = (
        "LEGACY_FALLBACKS = {'tab': '#myTab a'}\n"
        "def f(page):\n"
        '    """A docstring that says #id and .class."""\n'
        "    page.locator('#myTab')\n"
        "    page.locator('.navbar-collapse')\n"
        "    page.locator('a[data-target=\"x\"]')\n"
        "    page.locator('[id=\"s2id_x\"]')\n"
        "    page.locator('div[class=\"x\"]')\n"
        "    page.locator('a[href=\"#x\"]')\n"
        "    page.locator('[name=\"title\"]')\n"
    )
    assert selectors_that_name_an_id_a_class_or_data(source) == [
        "#myTab",
        ".navbar-collapse",
        'a[data-target="x"]',
        '[id="s2id_x"]',
        'div[class="x"]',
    ]


def test_the_legacy_mapping_holds_the_selectors_that_the_check_forbids_elsewhere():
    # The mapping is where today's ids, classes and data attributes live, and
    # the only place they may.
    joined = " ".join(LEGACY_FALLBACKS.values())
    assert "#myTab" in joined
    assert "data-" in joined
    assert "s2id_" in joined


def test_the_legacy_mapping_is_read_only_by_the_shared_fallback_helper():
    tree = ast.parse(FLOW.read_text())
    readers = set()
    for function in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        for node in ast.walk(function):
            if isinstance(node, ast.Name) and node.id == "LEGACY_FALLBACKS":
                readers.add(function.name)
    assert readers == {"legacy_fallback"}
    # Outside every function (the definition aside) it is not read at all.
    names = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "LEGACY_FALLBACKS"
    ]
    assert len(names) == 2  # the assignment and the one read


def test_every_tab_the_steps_open_has_a_label():
    source = FLOW.read_text()
    opened = set(re.findall(r'open_tab\(state, "(\w+)"\)', source))
    opened |= set(re.findall(r'see\([^)]*, "(\w+)"\)', source)) & set(TAB_LABELS)
    assert opened
    assert opened <= set(TAB_LABELS), sorted(opened - set(TAB_LABELS))


def test_a_known_page_error_is_matched_by_its_exact_text_only():
    (text,) = KNOWN_PAGE_ERRORS
    assert known_page_error(PAGE_ERROR_PREFIX + text) == KNOWN_PAGE_ERRORS[text]
    # Not as a substring, not on another message and not as a console error.
    assert known_page_error(PAGE_ERROR_PREFIX + text + " again") is None
    assert known_page_error(PAGE_ERROR_PREFIX + "x " + text) is None
    assert known_page_error("console error: " + text) is None
    assert known_page_error(PAGE_ERROR_PREFIX + "_DT_CellIndex") is None


DAY = datetime.date(2026, 3, 5)


@pytest.mark.parametrize(
    "kind, placeholder, when, expected",
    [
        ("date", "", None, "2026-03-05"),
        ("datetime-local", "", datetime.time(9, 30), "2026-03-05T09:30"),
        ("datetime-local", "", None, "2026-03-05T00:00"),
        ("time", "", datetime.time(18, 0), "18:00"),
        ("text", "", None, "2026-03-05"),
        ("text", "", datetime.time(9, 0), "2026-03-05 09:00:00"),
        ("text", "dd/mm/yyyy", None, "05/03/2026"),
        ("text", "DD-MM-YYYY", None, "05-03-2026"),
        ("text", "mm/dd/yyyy", None, "03/05/2026"),
        ("text", "yyyy.mm.dd", None, "2026.03.05"),
        ("text", "dd/mm/yyyy", datetime.time(9, 0), "05/03/2026 09:00"),
        # A placeholder that is not a date layout is ignored.
        ("text", "Pick a day", None, "2026-03-05"),
        ("text", "dd/dd/yyyy", None, "2026-03-05"),
    ],
)
def test_format_date_follows_the_field(kind, placeholder, when, expected):
    assert format_date(DAY, kind, placeholder, when) == expected


@pytest.mark.parametrize(
    "shown",
    [
        "2026-03-05",
        "05/03/2026",
        "5/3/2026",
        "03/05/2026",
        "5 March 2026",
        "05 Mar 2026",
        "March 5, 2026",
        "Mar. 5, 2026",
    ],
)
def test_date_pattern_finds_the_date_however_it_is_written(shown):
    assert date_pattern(DAY).search(f"Closed on {shown}.")


@pytest.mark.parametrize(
    "shown", ["2026-03-15", "15/03/2026", "March 25, 2026", "2025-03-05"]
)
def test_date_pattern_does_not_find_another_day(shown):
    assert not date_pattern(DAY).search(shown)


def test_date_pattern_knows_the_months_the_admin_abbreviates():
    assert date_pattern(datetime.date(2026, 10, 14)).search("Oct. 14, 2026")
    assert date_pattern(datetime.date(2026, 9, 3)).search("Sept. 3, 2026")


@pytest.mark.parametrize(
    "when, shown",
    [
        (datetime.time(18, 0), "18:00"),
        (datetime.time(18, 0), "6 p.m."),
        (datetime.time(18, 0), "6:00 PM"),
        (datetime.time(18, 0), "6 pm"),
        (datetime.time(18, 45), "6:45 p.m."),
        (datetime.time(9, 30), "9:30 a.m."),
    ],
)
def test_time_pattern_finds_the_time_however_it_is_written(when, shown):
    assert time_pattern(when).search(f"Starts {shown}")


def test_time_pattern_does_not_find_another_time():
    assert not time_pattern(datetime.time(18, 0)).search("16 p.m. and 7 p.m.")
    assert not time_pattern(datetime.time(18, 0)).search("6 a.m.")
