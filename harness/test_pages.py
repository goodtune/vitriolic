import json
from types import SimpleNamespace

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
    "match-live-stream",
    "scorecard-report",
    "person-merge",
    "placeholder-list",
    "placeholder-add",
    "placeholder-edit",
    "media-list",
    "folder-edit",
    "folder-add",
    "application-edit",
    "application-add",
    "application-perms",
    "undecidedteam-edit",
    "undecidedteam-add",
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


@pytest.mark.django_db(transaction=True)
def test_every_model_and_route_left_out_says_why():
    seed()
    skipped = {s["model"]: s["reason"] for s in discover()["skipped"]}
    # The seed now fills the model it used to leave out.
    assert "UndecidedTeam" not in skipped
    # Place is the multi-table parent of Venue and Ground, and SeasonAssociation
    # is edited on its club's officials page: neither has a route of its own.
    assert "NotImplementedError" in skipped["Place"]
    assert "NotImplementedError" in skipped["SeasonAssociation"]
    assert any(page["name"] == "officials" for page in discover()["pages"])
    # Enabling an upstream would contact a remote host.
    assert "remote host" in skipped["upstream-sync"]
    assert all(reason for reason in skipped.values())


@pytest.mark.django_db(transaction=True)
def test_main_without_a_name_takes_it_from_the_database(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("VITRIOLIC_HARNESS_VAR", str(tmp_path))
    # Only what the function reads is replaced, not the live connection.
    monkeypatch.setattr(
        "harness.pages.settings",
        SimpleNamespace(DATABASES={"default": {"NAME": "vitriolic_Feat_X"}}),
    )
    seed()
    assert main([]) == 0
    assert (paths_for("feat_x")["state"] / "pages.json").is_file()
    assert "pages," in capsys.readouterr().out


def test_main_without_a_name_refuses_a_database_that_is_not_the_harness_s(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        "harness.pages.settings",
        SimpleNamespace(DATABASES={"default": {"NAME": "elsewhere"}}),
    )
    assert main([]) == 64
    assert "pass the name" in capsys.readouterr().err
