from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.services import mcp_service
from tests._helpers import recorded_argv, write_fake_cli


@pytest.fixture
def fake_bin(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return bin_dir


@pytest.fixture
def home(tmp_path, monkeypatch):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    return home_dir


# --- validation --------------------------------------------------------


def test_list_servers_rejects_unknown_engine(tmp_path):
    with pytest.raises(ValueError, match="Invalid engine"):
        mcp_service.list_servers("shell", str(tmp_path))


def test_add_server_rejects_unknown_engine(tmp_path):
    with pytest.raises(ValueError, match="Invalid engine"):
        mcp_service.add_server("shell", str(tmp_path), "name", command=["echo"])


def test_add_server_rejects_invalid_name(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "claude")
    with pytest.raises(ValueError, match="Invalid MCP server name"):
        mcp_service.add_server("claude", str(tmp_path), "bad name!", command=["echo"])


def test_add_server_requires_exactly_one_of_command_or_url(tmp_path):
    with pytest.raises(ValueError, match="Exactly one"):
        mcp_service.add_server("claude", str(tmp_path), "name")
    with pytest.raises(ValueError, match="Exactly one"):
        mcp_service.add_server(
            "claude", str(tmp_path), "name", command=["echo"], url="http://x"
        )


# --- reads (native config files) ----------------------------------------


def test_list_claude_reads_project_mcp_json(tmp_path):
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "srv1": {
                        "type": "stdio",
                        "command": "echo",
                        "args": ["hi"],
                        "env": {"FOO": "bar"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    servers = mcp_service.list_servers("claude", str(tmp_path))

    assert servers == [
        {
            "name": "srv1",
            "scope": "project",
            "transport": "stdio",
            "command": ["echo", "hi"],
            "url": None,
            "env": {"FOO": "bar"},
        }
    ]


def test_list_claude_missing_file_returns_empty(tmp_path):
    assert mcp_service.list_servers("claude", str(tmp_path)) == []


def test_list_gemini_reads_project_settings(tmp_path):
    gemini_dir = tmp_path / ".gemini"
    gemini_dir.mkdir()
    (gemini_dir / "settings.json").write_text(
        json.dumps({"mcpServers": {"srv1": {"command": "echo", "args": ["hi"]}}}),
        encoding="utf-8",
    )

    servers = mcp_service.list_servers("gemini", str(tmp_path))

    assert servers[0]["name"] == "srv1"
    assert servers[0]["scope"] == "project"
    assert servers[0]["command"] == ["echo", "hi"]


def test_list_codex_reads_global_config_toml(tmp_path, home):
    codex_dir = home / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(
        '[mcp_servers.srv1]\ncommand = "echo"\nargs = ["hi"]\n\n'
        '[mcp_servers.srv1.env]\nFOO = "bar"\n',
        encoding="utf-8",
    )

    servers = mcp_service.list_servers("codex", "/any/project")

    assert servers == [
        {
            "name": "srv1",
            "scope": "global",
            "transport": "stdio",
            "command": ["echo", "hi"],
            "url": None,
            "env": {"FOO": "bar"},
        }
    ]


def test_list_opencode_reads_global_config(tmp_path, home):
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    (config_dir / "opencode.json").write_text(
        json.dumps(
            {
                "mcp": {
                    "srv1": {
                        "type": "local",
                        "command": ["echo", "hi"],
                        "environment": {"FOO": "bar"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    servers = mcp_service.list_servers("opencode", "/any/project")

    assert servers == [
        {
            "name": "srv1",
            "scope": "global",
            "transport": "local",
            "command": ["echo", "hi"],
            "url": None,
            "env": {"FOO": "bar"},
        }
    ]


# --- mutations: add via CLI ---------------------------------------------


def test_add_server_claude_builds_expected_argv(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "claude")

    mcp_service.add_server(
        "claude", str(tmp_path), "srv1", command=["echo", "hi"], env={"FOO": "bar"}
    )

    argv = recorded_argv(fake_bin, "claude")
    # name must precede -e (variadic) or claude misparses it — see module docstring.
    assert argv == [
        "mcp",
        "add",
        "--scope",
        "project",
        "srv1",
        "-e",
        "FOO=bar",
        "--",
        "echo",
        "hi",
    ]


def test_add_server_codex_builds_expected_argv(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "codex")

    mcp_service.add_server(
        "codex", str(tmp_path), "srv1", command=["echo", "hi"], env={"FOO": "bar"}
    )

    argv = recorded_argv(fake_bin, "codex")
    assert argv == ["mcp", "add", "srv1", "--env", "FOO=bar", "--", "echo", "hi"]


def test_add_server_gemini_builds_expected_argv(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "gemini")

    mcp_service.add_server(
        "gemini", str(tmp_path), "srv1", command=["echo", "hi"], env={"FOO": "bar"}
    )

    argv = recorded_argv(fake_bin, "gemini")
    assert argv == [
        "mcp",
        "add",
        "--scope",
        "project",
        "srv1",
        "-e",
        "FOO=bar",
        "echo",
        "hi",
    ]


def test_add_server_opencode_builds_expected_argv(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "opencode")

    mcp_service.add_server(
        "opencode", str(tmp_path), "srv1", command=["echo", "hi"], env={"FOO": "bar"}
    )

    argv = recorded_argv(fake_bin, "opencode")
    assert argv == ["mcp", "add", "srv1", "--env", "FOO=bar", "--", "echo", "hi"]


def test_add_server_url_variant(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "codex")

    mcp_service.add_server(
        "codex", str(tmp_path), "srv1", url="https://example.com/mcp"
    )

    argv = recorded_argv(fake_bin, "codex")
    assert argv == ["mcp", "add", "srv1", "--url", "https://example.com/mcp"]


def test_add_server_raises_on_cli_failure(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "claude", exit_code=1, stderr="boom")

    with pytest.raises(RuntimeError, match="boom"):
        mcp_service.add_server("claude", str(tmp_path), "srv1", command=["echo"])


def test_add_server_raises_when_cli_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(RuntimeError, match="not found on PATH"):
        mcp_service.add_server("claude", str(tmp_path), "srv1", command=["echo"])


# --- mutations: remove -------------------------------------------------


def test_remove_server_claude_via_cli(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "claude")

    mcp_service.remove_server("claude", str(tmp_path), "srv1")

    assert recorded_argv(fake_bin, "claude") == ["mcp", "remove", "srv1"]


def test_remove_server_codex_via_cli(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "codex")

    mcp_service.remove_server("codex", str(tmp_path), "srv1")

    assert recorded_argv(fake_bin, "codex") == ["mcp", "remove", "srv1"]


def test_remove_server_gemini_via_file_edit_preserves_others(tmp_path):
    gemini_dir = tmp_path / ".gemini"
    gemini_dir.mkdir()
    settings_path = gemini_dir / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "otherKey": "keep-me",
                "mcpServers": {
                    "srv1": {"command": "echo"},
                    "srv2": {"command": "ls"},
                },
            }
        ),
        encoding="utf-8",
    )

    mcp_service.remove_server("gemini", str(tmp_path), "srv1")

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["otherKey"] == "keep-me"
    assert list(data["mcpServers"].keys()) == ["srv2"]


def test_remove_server_gemini_missing_raises_key_error(tmp_path):
    gemini_dir = tmp_path / ".gemini"
    gemini_dir.mkdir()
    (gemini_dir / "settings.json").write_text(
        json.dumps({"mcpServers": {}}), encoding="utf-8"
    )

    with pytest.raises(KeyError):
        mcp_service.remove_server("gemini", str(tmp_path), "does-not-exist")


def test_remove_server_opencode_via_file_edit_preserves_others(tmp_path, home):
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "opencode.json"
    config_path.write_text(
        json.dumps(
            {
                "model": "keep-me",
                "mcp": {
                    "srv1": {"type": "local", "command": ["echo"]},
                    "srv2": {"type": "local", "command": ["ls"]},
                },
            }
        ),
        encoding="utf-8",
    )

    mcp_service.remove_server("opencode", "/any/project", "srv1")

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["model"] == "keep-me"
    assert list(data["mcp"].keys()) == ["srv2"]
