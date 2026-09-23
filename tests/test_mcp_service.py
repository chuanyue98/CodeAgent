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


def test_list_codebuddy_reads_project_mcp_json(tmp_path):
    # codebuddy's project scope shares claude's ``.mcp.json`` filename
    # (verified live); entries may carry codebuddy-specific extras
    # (``print``) which normalization ignores.
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "srv1": {
                        "type": "stdio",
                        "command": "echo",
                        "args": ["hi"],
                        "env": {"FOO": "bar"},
                        "print": True,
                    }
                },
                "disabledMcpServers": [],
            }
        ),
        encoding="utf-8",
    )

    servers = mcp_service.list_servers("codebuddy", str(tmp_path))

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


def test_list_codebuddy_missing_file_returns_empty(tmp_path):
    assert mcp_service.list_servers("codebuddy", str(tmp_path)) == []


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


def test_list_opencode_reads_jsonc_config(tmp_path, home):
    """opencode 1.18 writes opencode.jsonc; reading only .json hid every server."""
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    (config_dir / "opencode.jsonc").write_text(
        json.dumps({"mcp": {"srv1": {"type": "local", "command": ["echo", "hi"]}}}),
        encoding="utf-8",
    )

    servers = mcp_service.list_servers("opencode", "/any/project")

    assert [s["name"] for s in servers] == ["srv1"]


def test_list_opencode_tolerates_comments_in_jsonc(tmp_path, home):
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    (config_dir / "opencode.jsonc").write_text(
        "{\n"
        "  // the filesystem server\n"
        '  "mcp": {\n'
        '    "srv1": {"type": "remote", "url": "https://example.com/mcp"}\n'
        "  }\n"
        "  /* trailing block comment */\n"
        "}\n",
        encoding="utf-8",
    )

    servers = mcp_service.list_servers("opencode", "/any/project")

    # The // inside "https://..." must not be mistaken for a comment.
    assert servers[0]["url"] == "https://example.com/mcp"


def test_opencode_jsonc_wins_over_json_when_both_exist(tmp_path, home):
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    (config_dir / "opencode.json").write_text(
        json.dumps({"mcp": {"stale": {"command": ["old"]}}}), encoding="utf-8"
    )
    (config_dir / "opencode.jsonc").write_text(
        json.dumps({"mcp": {"current": {"command": ["new"]}}}), encoding="utf-8"
    )

    servers = mcp_service.list_servers("opencode", "/any/project")

    assert [s["name"] for s in servers] == ["current"]


def test_remove_opencode_refuses_to_destroy_comments(tmp_path, home):
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "opencode.jsonc"
    original = '{\n  // keep me\n  "mcp": {"srv1": {"command": ["echo"]}}\n}\n'
    config_path.write_text(original, encoding="utf-8")

    with pytest.raises(RuntimeError, match="contains comments"):
        mcp_service.remove_server("opencode", "/any/project", "srv1")

    assert config_path.read_text(encoding="utf-8") == original


def test_list_antigravity_reads_config(tmp_path, home):
    cfg_dir = home / ".gemini" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "mcp_config.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "srv1": {
                        "command": "echo",
                        "args": ["hi"],
                        "env": {"FOO": "bar"},
                    },
                    "srv2": {
                        "serverUrl": "https://example.com/mcp",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    servers = mcp_service.list_servers("antigravity", "/any/project")

    assert servers == [
        {
            "name": "srv1",
            "scope": "user",
            "transport": "stdio",
            "command": ["echo", "hi"],
            "url": None,
            "env": {"FOO": "bar"},
        },
        {
            "name": "srv2",
            "scope": "user",
            "transport": "http",
            "command": None,
            "url": "https://example.com/mcp",
            "env": {},
        },
    ]


def test_list_antigravity_missing_file_returns_empty(tmp_path, home):
    assert mcp_service.list_servers("antigravity", "/any/project") == []


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


def test_add_server_opencode_builds_expected_argv(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "opencode")

    mcp_service.add_server(
        "opencode", str(tmp_path), "srv1", command=["echo", "hi"], env={"FOO": "bar"}
    )

    argv = recorded_argv(fake_bin, "opencode")
    assert argv == ["mcp", "add", "srv1", "--env", "FOO=bar", "--", "echo", "hi"]


def test_add_server_codebuddy_builds_expected_argv(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "codebuddy")

    mcp_service.add_server(
        "codebuddy", str(tmp_path), "srv1", command=["echo", "hi"], env={"FOO": "bar"}
    )

    argv = recorded_argv(fake_bin, "codebuddy")
    assert argv == [
        "mcp",
        "add",
        "-s",
        "project",
        "srv1",
        "-e",
        "FOO=bar",
        "--",
        "echo",
        "hi",
    ]


def test_add_server_antigravity_builds_expected_argv(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "agy")

    mcp_service.add_server(
        "antigravity",
        str(tmp_path),
        "srv1",
        command=["echo", "hi"],
        env={"FOO": "bar"},
    )

    argv = recorded_argv(fake_bin, "agy")
    assert argv == [
        "mcp",
        "add",
        "--env",
        "FOO=bar",
        "srv1",
        "--",
        "echo",
        "hi",
    ]


def test_add_server_antigravity_url_variant(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "agy")

    mcp_service.add_server(
        "antigravity", str(tmp_path), "srv1", url="https://example.com/mcp"
    )

    argv = recorded_argv(fake_bin, "agy")
    assert argv == ["mcp", "add", "srv1", "https://example.com/mcp"]


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


def test_remove_server_codebuddy_via_cli(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "codebuddy")

    mcp_service.remove_server("codebuddy", str(tmp_path), "srv1")

    assert recorded_argv(fake_bin, "codebuddy") == [
        "mcp",
        "remove",
        "srv1",
        "-s",
        "project",
    ]


def test_remove_server_antigravity_builds_expected_argv(tmp_path, fake_bin):
    write_fake_cli(fake_bin, "agy")

    mcp_service.remove_server("antigravity", str(tmp_path), "srv1")

    assert recorded_argv(fake_bin, "agy") == ["mcp", "remove", "srv1"]


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


# --- cross-engine sync ---------------------------------------------------


@pytest.fixture
def calls(monkeypatch):
    """Captures add/remove calls so sync can be asserted without any real CLI."""
    recorded: list[tuple] = []

    def fake_add(engine, project_path, name, **kwargs):
        recorded.append(("add", engine, name, kwargs))

    def fake_remove(engine, project_path, name):
        recorded.append(("remove", engine, name))

    monkeypatch.setattr(mcp_service, "add_server", fake_add)
    monkeypatch.setattr(mcp_service, "remove_server", fake_remove)
    return recorded


def _write_claude_source(project: Path, servers: dict) -> None:
    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": servers}), encoding="utf-8"
    )


def test_sync_defaults_to_every_other_engine(tmp_path, home, calls):
    _write_claude_source(tmp_path, {"srv1": {"command": "echo", "args": ["hi"]}})

    results = mcp_service.sync_servers("claude", str(tmp_path))

    assert {r["engine"] for r in results} == {
        "codex",
        "opencode",
        "codebuddy",
        "antigravity",
    }
    # codebuddy's project scope IS claude's ``.mcp.json`` (verified live), so
    # it already "has" srv1 and correctly reports skipped rather than added.
    for r in results:
        expected_action = "skipped" if r["engine"] == "codebuddy" else "added"
        assert r["action"] == expected_action
    assert {engine for kind, engine, *_ in calls if kind == "add"} == {
        "codex",
        "opencode",
        "antigravity",
    }


def test_sync_forwards_command_and_env(tmp_path, home, calls):
    _write_claude_source(
        tmp_path,
        {"srv1": {"command": "echo", "args": ["hi"], "env": {"FOO": "bar"}}},
    )

    mcp_service.sync_servers("claude", str(tmp_path), targets=["opencode"])

    assert calls == [
        (
            "add",
            "opencode",
            "srv1",
            {"command": ["echo", "hi"], "transport": None, "env": {"FOO": "bar"}},
        )
    ]


def test_sync_honors_explicit_targets_and_names(tmp_path, home, calls):
    _write_claude_source(
        tmp_path,
        {"srv1": {"command": "echo"}, "srv2": {"command": "ls"}},
    )

    results = mcp_service.sync_servers(
        "claude", str(tmp_path), targets=["codex"], names=["srv2"]
    )

    assert [(r["engine"], r["name"]) for r in results] == [("codex", "srv2")]
    assert [c[1:3] for c in calls] == [("codex", "srv2")]


def test_sync_rejects_source_as_its_own_target(tmp_path):
    with pytest.raises(ValueError, match="onto itself"):
        mcp_service.sync_servers("claude", str(tmp_path), targets=["claude"])


def test_sync_rejects_unknown_target_engine(tmp_path):
    with pytest.raises(ValueError, match="Invalid engine"):
        mcp_service.sync_servers("claude", str(tmp_path), targets=["shell"])


def test_sync_rejects_unknown_server_name(tmp_path, home):
    _write_claude_source(tmp_path, {"srv1": {"command": "echo"}})

    with pytest.raises(ValueError, match="No such MCP server"):
        mcp_service.sync_servers("claude", str(tmp_path), names=["nope"])


def test_sync_skips_existing_by_default(tmp_path, home, calls):
    _write_claude_source(tmp_path, {"srv1": {"command": "echo"}})
    opencode_dir = home / ".config" / "opencode"
    opencode_dir.mkdir(parents=True, exist_ok=True)
    (opencode_dir / "opencode.json").write_text(
        json.dumps({"mcp": {"srv1": {"type": "local", "command": ["other"]}}}),
        encoding="utf-8",
    )

    results = mcp_service.sync_servers("claude", str(tmp_path), targets=["opencode"])

    assert results[0]["action"] == "skipped"
    assert calls == []


def test_sync_overwrite_removes_then_adds(tmp_path, home, calls):
    _write_claude_source(tmp_path, {"srv1": {"command": "echo"}})
    opencode_dir = home / ".config" / "opencode"
    opencode_dir.mkdir(parents=True, exist_ok=True)
    (opencode_dir / "opencode.json").write_text(
        json.dumps({"mcp": {"srv1": {"type": "local", "command": ["other"]}}}),
        encoding="utf-8",
    )

    results = mcp_service.sync_servers(
        "claude", str(tmp_path), targets=["opencode"], overwrite=True
    )

    assert results[0]["action"] == "replaced"
    assert [c[0] for c in calls] == ["remove", "add"]


def test_sync_dry_run_writes_nothing(tmp_path, home, calls):
    _write_claude_source(tmp_path, {"srv1": {"command": "echo"}})

    results = mcp_service.sync_servers(
        "claude", str(tmp_path), targets=["codex"], dry_run=True
    )

    assert results[0]["action"] == "added"
    assert "would be added" in results[0]["detail"]
    assert calls == []


def test_sync_isolates_per_engine_failures(tmp_path, home, monkeypatch):
    _write_claude_source(tmp_path, {"srv1": {"command": "echo"}})

    def flaky_add(engine, project_path, name, **kwargs):
        if engine == "codex":
            raise RuntimeError("'codex' CLI not found on PATH")

    monkeypatch.setattr(mcp_service, "add_server", flaky_add)

    results = mcp_service.sync_servers(
        "claude", str(tmp_path), targets=["codex", "opencode"]
    )

    by_engine = {r["engine"]: r for r in results}
    assert by_engine["codex"]["action"] == "failed"
    assert "not found on PATH" in by_engine["codex"]["detail"]
    assert by_engine["opencode"]["action"] == "added"


def test_sync_reports_data_loss_when_overwrite_readd_fails(tmp_path, home, monkeypatch):
    _write_claude_source(tmp_path, {"srv1": {"command": "echo"}})
    opencode_dir = home / ".config" / "opencode"
    opencode_dir.mkdir(parents=True, exist_ok=True)
    (opencode_dir / "opencode.json").write_text(
        json.dumps({"mcp": {"srv1": {"type": "local", "command": ["other"]}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_service, "remove_server", lambda *a, **k: None)
    monkeypatch.setattr(
        mcp_service,
        "add_server",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    results = mcp_service.sync_servers(
        "claude", str(tmp_path), targets=["opencode"], overwrite=True
    )

    assert results[0]["action"] == "failed"
    assert "removed existing entry but re-add failed" in results[0]["detail"]


def test_sync_normalizes_opencode_local_transport(tmp_path, home, calls):
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    (config_dir / "opencode.json").write_text(
        json.dumps({"mcp": {"srv1": {"type": "local", "command": ["echo", "hi"]}}}),
        encoding="utf-8",
    )

    mcp_service.sync_servers("opencode", str(tmp_path), targets=["claude"])

    # "local" is opencode's own word for stdio and must not reach claude's
    # --transport flag, which would reject it.
    assert calls[0][3]["transport"] is None
    assert calls[0][3]["command"] == ["echo", "hi"]


def test_sync_maps_remote_transport_to_http(tmp_path, home, calls):
    _write_claude_source(
        tmp_path, {"srv1": {"type": "remote", "url": "https://example.com/mcp"}}
    )

    mcp_service.sync_servers("claude", str(tmp_path), targets=["opencode"])

    assert calls[0][3] == {
        "url": "https://example.com/mcp",
        "transport": "http",
        "env": {},
    }


def test_sync_preserves_sse_transport(tmp_path, home, calls):
    _write_claude_source(
        tmp_path, {"srv1": {"type": "sse", "url": "https://example.com/sse"}}
    )

    mcp_service.sync_servers("claude", str(tmp_path), targets=["opencode"])

    assert calls[0][3]["transport"] == "sse"


def test_sync_fails_entry_with_neither_command_nor_url(tmp_path, home, calls):
    _write_claude_source(tmp_path, {"srv1": {"type": "stdio"}})

    results = mcp_service.sync_servers("claude", str(tmp_path), targets=["opencode"])

    assert results[0]["action"] == "failed"
    assert "neither a command nor a url" in results[0]["detail"]
    assert calls == []


def test_sync_sees_existing_opencode_servers_in_jsonc(tmp_path, home, calls):
    """Regression: the .json-only read made every opencode target look empty,
    so sync re-added servers that were already configured."""
    _write_claude_source(tmp_path, {"srv1": {"command": "echo"}})
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    (config_dir / "opencode.jsonc").write_text(
        json.dumps({"mcp": {"srv1": {"type": "local", "command": ["echo"]}}}),
        encoding="utf-8",
    )

    results = mcp_service.sync_servers("claude", str(tmp_path), targets=["opencode"])

    assert results[0]["action"] == "skipped"
    assert calls == []


def test_sync_with_no_source_servers_returns_empty(tmp_path, home, calls):
    _write_claude_source(tmp_path, {})

    assert mcp_service.sync_servers("claude", str(tmp_path)) == []
    assert calls == []
