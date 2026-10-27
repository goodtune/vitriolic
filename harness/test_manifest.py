import json
import subprocess

import pytest

from harness.manifest import Manifest, PageResult
from harness.paths import paths_for
from harness.shots import (
    head_commit,
    main,
    parse_only,
    prepare_out,
    run_directory,
    select_pages,
)


def test_manifest_round_trip_and_failed(tmp_path):
    m = Manifest(name="x", brand="default", base="http://127.0.0.1:1")
    m.pages.append(
        PageResult(
            name="index",
            url="/admin/",
            width=1440,
            status=500,
            title="",
            errors=["HTTP 500"],
            warnings=[],
            file="index-1440.png",
        )
    )
    m.write(tmp_path / "manifest.json")
    again = Manifest.read(tmp_path / "manifest.json")
    assert again.failed is True
    assert again.pages[0].errors == ["HTTP 500"]


def test_manifest_without_errors_has_not_failed():
    m = Manifest(name="x", brand="default", base="http://127.0.0.1:1")
    m.pages.append(
        PageResult(
            name="index",
            url="/admin/",
            width=1440,
            status=200,
            title="Admin",
            errors=[],
            warnings=["failed request to https://example.com/a.png"],
            file="index-1440.png",
        )
    )
    assert m.failed is False


def test_prepare_out_refuses_a_foreign_directory(tmp_path):
    (tmp_path / "notes.txt").write_text("mine")
    with pytest.raises(SystemExit, match="refusing to clear"):
        prepare_out(tmp_path, "rigtest", "default")
    Manifest(name="rigtest", brand="default", base="x").write(
        tmp_path / "manifest.json"
    )
    (tmp_path / "notes.txt").unlink()
    prepare_out(tmp_path, "rigtest", "default")
    assert list(tmp_path.iterdir()) == []


def test_prepare_out_refuses_another_brand(tmp_path):
    Manifest(name="rigtest", brand="forest", base="x").write(tmp_path / "manifest.json")
    with pytest.raises(SystemExit, match="refusing to clear"):
        prepare_out(tmp_path, "rigtest", "default")


def test_prepare_out_creates_a_missing_directory(tmp_path):
    out = tmp_path / "run" / "rigtest" / "default"
    prepare_out(out, "rigtest", "default")
    assert out.is_dir()


def test_only_none_selects_no_pages_and_a_wrong_name_is_refused():
    pages = [{"name": "index"}, {"name": "season-edit"}]
    assert select_pages("none", pages) == set()
    assert select_pages("", pages) is None
    assert select_pages("index", pages) == {"index"}
    with pytest.raises(SystemExit):
        select_pages("indx", pages)


def captured(name, width, tab=0, file=True, errors=()):
    return PageResult(
        name=name,
        url=f"/admin/{name}/",
        width=width,
        status=200,
        title="",
        errors=list(errors),
        file=f"{name}-{width}.png" if file else "",
        tab=tab,
    )


def manifest_with(expected, widths, pages, **kwargs):
    m = Manifest(name="x", brand="default", base="b", **kwargs)
    m.expected_pages = expected
    m.widths = widths
    m.pages.extend(pages)
    return m


def test_a_run_that_captured_fewer_pages_than_were_listed_has_failed():
    pages = [captured("index", 1440), captured("index", 390), captured("login", 1440)]
    m = manifest_with(2, [1440, 390], pages)
    assert m.captured == 3
    assert m.incomplete is True
    assert m.failed is True
    # Capturing every page at every width is complete, with no errors.
    m.pages.append(captured("login", 390))
    assert m.incomplete is False
    assert m.failed is False


def test_tabs_and_pictures_that_were_not_saved_do_not_count_as_pages():
    pages = [
        captured("index", 1440),
        captured("index-tab-1", 1440, tab=1),
        captured("login", 1440, file=False, errors=["failed to load: x"]),
    ]
    m = manifest_with(2, [1440], pages)
    assert m.captured == 1
    assert m.incomplete is True


def test_a_run_limited_by_only_is_not_incomplete_for_that():
    m = manifest_with(150, [1440, 390], [captured("index", 1440)], only=["index"])
    assert m.incomplete is False
    assert m.failed is False
    flow_only = manifest_with(150, [1440], [], only=[])
    assert flow_only.failed is False


def test_an_error_of_the_run_itself_fails_it():
    m = manifest_with(0, [1440], [], only=[])
    m.errors.append("nothing answers on port 8300")
    assert m.error_count == 1
    assert m.failed is True


def test_the_metadata_survives_the_round_trip(tmp_path):
    m = manifest_with(
        3,
        [1440, 390],
        [captured("index", 1440)],
        only=["index"],
        video=False,
        checkout="/work/harness",
        commit="abc123",
        htmx_tabs=True,
    )
    m.flow_stamps = {"1440": "101010"}
    m.errors.append("boom")
    m.write(tmp_path / "manifest.json")
    again = Manifest.read(tmp_path / "manifest.json")
    assert again.only == ["index"]
    assert again.widths == [1440, 390]
    assert again.video is False
    assert again.expected_pages == 3
    assert (again.checkout, again.commit) == ("/work/harness", "abc123")
    assert again.htmx_tabs is True
    assert again.flow_stamps == {"1440": "101010"}
    assert again.errors == ["boom"]
    assert again.pages[0].tab == 0


def test_a_manifest_from_before_the_metadata_still_reads(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"name": "x", "brand": "default", "base": "b", "pages": []})
    )
    again = Manifest.read(tmp_path / "manifest.json")
    assert again.only is None
    assert again.htmx_tabs is False


def test_prepare_out_refuses_a_manifest_that_is_not_an_object(tmp_path):
    (tmp_path / "manifest.json").write_text("[1, 2]")
    with pytest.raises(SystemExit, match="refusing to clear"):
        prepare_out(tmp_path, "rigtest", "default")
    (tmp_path / "manifest.json").write_text('{"pages": [3]}')
    with pytest.raises(SystemExit, match="refusing to clear"):
        prepare_out(tmp_path, "rigtest", "default")


def test_prepare_out_keeps_the_html_tab_runs_apart(tmp_path):
    Manifest(name="rigtest", brand="default", base="x", htmx_tabs=True).write(
        tmp_path / "manifest.json"
    )
    with pytest.raises(SystemExit, match="refusing to clear"):
        prepare_out(tmp_path, "rigtest", "default", htmx_tabs=False)
    prepare_out(tmp_path, "rigtest", "default", htmx_tabs=True)
    assert list(tmp_path.iterdir()) == []


def test_runs_go_in_a_directory_for_the_brand_shell_and_tab_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("VITRIOLIC_HARNESS_VAR", str(tmp_path))
    runs = paths_for("rigtest")["runs"]
    assert run_directory("rigtest", "forest", "workbook", False) == runs / (
        "forest-workbook"
    )
    assert run_directory("RigTest", "forest", "explorer", True) == runs / (
        "forest-explorer-htmx"
    )


def test_prepare_out_refuses_another_shell(tmp_path):
    Manifest(name="rigtest", brand="default", shell="explorer", base="x").write(
        tmp_path / "manifest.json"
    )
    with pytest.raises(SystemExit):
        prepare_out(tmp_path, "rigtest", "default", False, "workbook")


def test_only_is_recorded_as_a_sorted_list_none_for_every_page():
    assert parse_only("") is None
    assert parse_only("none") == []
    assert parse_only("b,a,b") == ["a", "b"]


def test_head_commit_is_the_commit_of_the_checkout_or_unknown(tmp_path):
    assert head_commit(tmp_path) == "unknown"
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert head_commit(tmp_path) == "unknown"  # no commit yet
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=T",
            "-c",
            "user.email=t@example.org",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "x",
        ],
        check=True,
    )
    assert len(head_commit(tmp_path)) == 40


def arguments(out, *more):
    return [
        "--name",
        "rigtest",
        "--base",
        "http://127.0.0.1:1",
        "--brand",
        "default",
        "--out",
        str(out),
        *more,
    ]


def test_a_run_that_cannot_start_leaves_its_manifest_and_none_of_the_last_run(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("VITRIOLIC_HARNESS_VAR", str(tmp_path / "var"))
    out = tmp_path / "run"
    # What an earlier run of the same name and brand left behind.
    Manifest(name="rigtest", brand="default", base="b").write(out / "manifest.json")
    (out / "index-1440.png").write_text("an old picture")
    with pytest.raises(OSError):
        main(arguments(out, "--pages", str(tmp_path / "missing.json")))
    assert [p.name for p in out.iterdir()] == ["manifest.json"]
    left = Manifest.read(out / "manifest.json")
    assert left.failed is True
    assert left.finished
    assert "could not start" in left.errors[0]
    assert left.checkout and left.commit
    assert left.widths == [1440, 390]


def test_prepare_clears_the_directory_and_fail_records_why(tmp_path, monkeypatch):
    monkeypatch.setenv("VITRIOLIC_HARNESS_VAR", str(tmp_path / "var"))
    out = tmp_path / "run"
    Manifest(name="rigtest", brand="default", base="b").write(out / "manifest.json")
    (out / "index-1440.png").write_text("an old picture")
    assert main(arguments(out, "--prepare", "--only", "index", "--no-video")) == 0
    assert [p.name for p in out.iterdir()] == ["manifest.json"]
    started = Manifest.read(out / "manifest.json")
    assert (started.only, started.video, started.errors) == (["index"], False, [])
    assert main(arguments(out, "--fail", "nothing answers on port 1")) == 1
    failed = Manifest.read(out / "manifest.json")
    assert failed.errors == ["nothing answers on port 1"]
    assert failed.failed is True
    assert failed.finished
