import subprocess
from pathlib import Path

import pytest

from harness.paths import normalise, paths_for, var_root

LIB = Path(__file__).resolve().parent / "lib.sh"


def bash_name(name: str) -> tuple[int, str]:
    """What ``harness_name`` makes of ``name``: its exit status and output."""
    done = subprocess.run(
        ["bash", "-c", 'source "$1"; harness_name "$2"', "bash", str(LIB), name],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, done.stdout.strip()


def test_normalise_lowercases_and_replaces():
    assert normalise("My-Branch.2") == "my_branch_2"


def test_paths_for_are_under_var_root(tmp_path, monkeypatch):
    monkeypatch.setenv("VITRIOLIC_HARNESS_VAR", str(tmp_path))
    p = paths_for("demo")
    assert p["media"] == tmp_path / "media" / "demo"
    assert p["runs"] == tmp_path / "run" / "demo"


def test_paths_for_normalises_the_name(tmp_path, monkeypatch):
    monkeypatch.setenv("VITRIOLIC_HARNESS_VAR", str(tmp_path))
    assert paths_for("Feat/X")["state"] == tmp_path / "state" / "feat_x"
    assert paths_for("demo")["log"] == tmp_path / "log" / "demo"
    assert paths_for("demo")["pid"] == tmp_path / "run" / "demo" / "pid"


def test_var_root_defaults_to_xdg_state_home(tmp_path, monkeypatch):
    monkeypatch.delenv("VITRIOLIC_HARNESS_VAR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert var_root() == tmp_path / "vitriolic-harness"


@pytest.mark.parametrize(
    "name",
    [
        "Upper-CASE",
        "feat/branch",
        "caf\u00e9",
        "\u65e5\u672c\u8a9ex",
        "a__b",
        "_edge_",
        "__lead",
        "trail__",
        "mixed.Dots-and Spaces",
        "plain",
    ],
)
def test_normalise_agrees_with_harness_name(name):
    status, text = bash_name(name)
    assert status == 0
    assert text == normalise(name)


@pytest.mark.parametrize("name", ["___", "", "-", "\u65e5\u672c"])
def test_a_name_with_nothing_left_is_refused_by_both(name):
    status, __ = bash_name(name)
    assert status == 2
    with pytest.raises(ValueError):
        normalise(name)
