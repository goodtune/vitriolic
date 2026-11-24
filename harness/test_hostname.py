import socket
import subprocess

from vitriolic.context_processors import site


def test_the_invented_hostname_replaces_the_machine_name(monkeypatch):
    monkeypatch.setenv("VITRIOLIC_DEMO_HOSTNAME", "demo.example")
    assert site(None) == {"hostname": "demo.example"}


def test_the_machine_name_is_shown_without_the_variable(monkeypatch):
    monkeypatch.delenv("VITRIOLIC_DEMO_HOSTNAME", raising=False)
    assert site(None) == {"hostname": socket.gethostname()}


def test_harness_env_sets_an_invented_hostname(monkeypatch):
    monkeypatch.delenv("VITRIOLIC_DEMO_HOSTNAME", raising=False)
    out = subprocess.run(
        [
            "bash",
            "-c",
            'source harness/lib.sh; harness_env hosttest; printf %s "$VITRIOLIC_DEMO_HOSTNAME"',
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout == "demo.example"
