import pytest

from harness.manifest import Manifest, PageResult
from harness.shots import prepare_out


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
