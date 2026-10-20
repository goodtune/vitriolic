import json

import pytest

from harness.pages import discover, main
from harness.paths import paths_for
from harness.seeding import seed
from tournamentcontrol.competition.models import Season

EXPECTED = (
    "index",
    "login",
    "competition-index",
    "enrolment-index",
    "settings-index",
    "season-edit",
    "division-edit",
    "match-edit",
    "team-edit",
    "article-edit",
    "page-edit",
    "classgroup-edit",
    "reportcard-edit",
    "user-list",
    "user-edit",
    "group-list",
    "group-edit",
    "match-results",
    "match-visual-schedule",
)


@pytest.mark.django_db(transaction=True)
def test_discover_covers_every_admin_url_model():
    seed()
    found = discover()
    names = {p["name"] for p in found["pages"]}
    for expected in EXPECTED:
        assert expected in names, expected
    skipped = {s["model"] for s in found["skipped"]}
    # Score has no AdminUrlMixin, so it is never considered: it is not skipped.
    assert "Score" not in skipped
    assert all(p["url"].startswith("/admin/") for p in found["pages"])
    assert len({p["name"] for p in found["pages"]}) == len(found["pages"])
    assert all(s["reason"] for s in found["skipped"])


@pytest.mark.django_db(transaction=True)
def test_discover_picks_the_current_season_and_marks_the_tabbed_pages():
    seed()
    pages = {p["name"]: p for p in discover()["pages"]}
    spring = Season.objects.get(title="Spring 2026")
    assert pages["season-edit"]["url"] == str(spring.urls["edit"])
    assert pages["match-grid"]["url"].endswith("/grid.html")
    tabbed = {name for name, page in pages.items() if page.get("tabs")}
    assert tabbed == {
        "season-edit",
        "division-edit",
        "club-edit",
        "classgroup-edit",
        "enrolment-edit",
    }


@pytest.mark.django_db(transaction=True)
def test_main_writes_the_pages_under_the_state_directory(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("VITRIOLIC_HARNESS_VAR", str(tmp_path))
    seed()
    assert main(["Unit Test"]) == 0
    written = json.loads((paths_for("unit_test")["state"] / "pages.json").read_text())
    assert written == json.loads(json.dumps(discover()))
    assert "%d pages" % len(written["pages"]) in capsys.readouterr().out
