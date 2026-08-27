"""The launching agent's session must not follow CodeAgent into the engine."""

from pathlib import Path

import pytest

from core.host_env import HOST_SESSION_MARKERS, child_environ, strip_host_markers


def test_nested_session_flags_are_dropped():
    env = strip_host_markers({"CLAUDECODE": "1", "CLAUDE_CODE_CHILD_SESSION": "1"})
    assert env == {}


def test_the_host_control_channel_and_its_credential_are_dropped():
    env = strip_host_markers(
        {
            "CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/host.sock",
            "CLAUDE_CODE_MESSAGING_TOKEN": "secret",
            "CLAUDE_CODE_SESSION_ID": "host-session",
        }
    )
    assert env == {}


@pytest.mark.parametrize(
    "name",
    ["PATH", "HOME", "ANTHROPIC_API_KEY", "CLAUDE_CONFIG_DIR", "HTTP_PROXY"],
)
def test_user_configuration_and_credentials_pass_through(name):
    """Stripping these would break auth or the engine's own configuration."""
    assert strip_host_markers({name: "value"}) == {name: "value"}


def test_the_persistence_override_survives():
    """A user asking for transcripts must not be silently overruled.

    This is why the deny list is explicit rather than a `CLAUDE_CODE_*` sweep.
    """
    env = {"CLAUDE_CODE_FORCE_SESSION_PERSISTENCE": "1"}
    assert strip_host_markers(env) == env


def test_the_source_mapping_is_not_mutated():
    original = {"CLAUDECODE": "1", "PATH": "/bin"}
    strip_host_markers(original)
    assert original == {"CLAUDECODE": "1", "PATH": "/bin"}


def test_child_environ_reads_the_real_environment(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_TOKEN", "secret")
    monkeypatch.setenv("CA_TEST_PASSTHROUGH", "kept")

    env = child_environ()

    assert "CLAUDECODE" not in env
    assert "CLAUDE_CODE_MESSAGING_TOKEN" not in env
    assert env["CA_TEST_PASSTHROUGH"] == "kept"


def test_every_launch_path_sanitizes(monkeypatch):
    """Guards the wiring, not the helper: a new launch site that reaches for
    os.environ directly is the way this regresses."""
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "host-session")

    from core.cli.helpers import build_proxy_env
    from core.engine_base.environment import EnvironmentManager

    proxy_env, _, _, _ = build_proxy_env({"proxy": {"host": "127.0.0.1", "port": 1}})
    assert not HOST_SESSION_MARKERS & proxy_env.keys()

    engine_env = EnvironmentManager(root_dir=Path.cwd()).get_env()
    assert not HOST_SESSION_MARKERS & engine_env.keys()
