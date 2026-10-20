from harness.paths import normalise, paths_for, var_root


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
