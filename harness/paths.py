"""Where the harness keeps the things a name owns.

``lib.sh`` computes the same locations in bash. Python modules in the harness
import this one and never recompute them.
"""

import os
import re
from pathlib import Path

DEFAULT_PG_PORT = 55432


def normalise(name: str) -> str:
    """Lower-case a name to ``[a-z0-9_]``, as ``harness_name`` does in bash.

    Works on bytes so that it agrees with ``tr`` for non-ASCII input.
    """
    cleaned = re.sub(rb"[^a-z0-9_]", b"_", name.encode().lower()).decode().strip("_")
    if not cleaned:
        raise ValueError(f"name {name!r} is empty once normalised")
    return cleaned


def var_root() -> Path:
    """The state root: ``$VITRIOLIC_HARNESS_VAR`` or under ``$XDG_STATE_HOME``."""
    override = os.environ.get("VITRIOLIC_HARNESS_VAR")
    if override:
        return Path(override)
    state_home = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    return Path(state_home) / "vitriolic-harness"


def paths_for(name: str) -> dict[str, Path]:
    """Everything a name owns on disk, under the state root."""
    name = normalise(name)
    root = var_root()
    runs = root / "run" / name
    return {
        "media": root / "media" / name,
        "log": root / "log" / name,
        "pid": runs / "pid",
        "state": root / "state" / name,
        "runs": runs,
    }


def database_name(name: str) -> str:
    return f"vitriolic_{normalise(name)}"
