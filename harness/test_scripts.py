import os
import subprocess
import time
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent
PORT = 19876


def bash(script: str, *args: str, var: Path | None = None):
    env = dict(os.environ)
    if var is not None:
        env["VITRIOLIC_HARNESS_VAR"] = str(var)
    return subprocess.run(
        ["bash", "-c", script, "bash", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


class FakeServer:
    """A process that is no child of the test, as a server serve.sh started is."""

    def __init__(self, pid: int):
        self.pid = pid

    def alive(self) -> bool:
        try:
            os.kill(self.pid, 0)
        except OSError:
            return False
        return True

    def poll(self):
        return None if self.alive() else 0

    def wait(self, timeout: float) -> int:
        deadline = time.monotonic() + timeout
        while self.alive() and time.monotonic() < deadline:
            time.sleep(0.1)
        return 0


@pytest.fixture
def fake_server():
    """A process whose command line looks like the demo project's runserver."""
    done = subprocess.run(
        [
            "bash",
            "-c",
            f"(exec -a 'python manage.py runserver 127.0.0.1:{PORT} --noreload' sleep 60) "
            ">/dev/null 2>&1 </dev/null & echo $!",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    server = FakeServer(int(done.stdout.strip()))
    time.sleep(0.5)
    yield server
    if server.alive():
        os.kill(server.pid, 9)


@pytest.mark.parametrize(
    "port, expected",
    [(str(PORT), 0), ("1987", 1), (str(PORT) + "0", 1), ("", 1)],
)
def test_runserver_is_matched_on_its_whole_address(fake_server, port, expected):
    done = bash(
        'source "$1"; harness_is_runserver "$2" "$3"',
        str(HARNESS / "lib.sh"),
        str(fake_server.pid),
        port,
    )
    assert done.returncode == expected


def test_a_pid_that_is_not_a_runserver_is_not_matched():
    done = bash(
        'source "$1"; harness_is_runserver "$$" "$2"', str(HARNESS / "lib.sh"), "8300"
    )
    assert done.returncode == 1


def write_pid_file(var: Path, pid: int, port: str) -> Path:
    run = var / "run" / "rigtest"
    run.mkdir(parents=True)
    pidfile = run / "pid"
    pidfile.write_text(
        f"pid={pid}\nport={port}\nbrand=default\nhtmx_tabs=0\ncheckout=/x\n"
    )
    return pidfile


def test_stop_stops_a_runserver_and_clears_its_pid_file(tmp_path, fake_server):
    pidfile = write_pid_file(tmp_path, fake_server.pid, str(PORT))
    done = bash('"$1" rigtest', str(HARNESS / "stop.sh"), var=tmp_path)
    assert done.returncode == 0
    assert "stopped 'rigtest'" in done.stdout
    assert fake_server.wait(timeout=10) is not None
    assert not pidfile.exists()


def test_stop_leaves_a_process_alone_when_the_pid_file_has_no_port(
    tmp_path, fake_server
):
    pidfile = write_pid_file(tmp_path, fake_server.pid, "")
    done = bash('"$1" rigtest', str(HARNESS / "stop.sh"), var=tmp_path)
    assert done.returncode == 0
    assert "is not running" in done.stdout
    assert fake_server.poll() is None
    assert not pidfile.exists()


def test_stop_leaves_a_process_alone_that_only_shares_a_port_prefix(
    tmp_path, fake_server
):
    write_pid_file(tmp_path, fake_server.pid, "1987")
    done = bash('"$1" rigtest', str(HARNESS / "stop.sh"), var=tmp_path)
    assert "is not running" in done.stdout
    assert fake_server.poll() is None
