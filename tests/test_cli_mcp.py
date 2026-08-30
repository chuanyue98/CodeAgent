"""``ca mcp list / add / remove / sync / serve`` 的 CLI 测试。"""

from pathlib import Path
from unittest.mock import patch

import pytest

import ca_launcher


def _run(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", *argv])
    return ca_launcher.main()


def _server(name, transport="stdio", command=None, url=None):
    return {"name": name, "transport": transport, "command": command, "url": url}


# ── ca mcp list ──────────────────────────────────────────────────────────────


def test_list_shows_every_engine_with_scope_and_servers(monkeypatch, capsys):
    def list_servers(engine, project_path):
        if engine == "claude":
            return [_server("fs", command=["npx", "fs-server"])]
        return []

    with patch("core.services.mcp_service.list_servers", side_effect=list_servers):
        _run(monkeypatch, "mcp", "list")

    out = capsys.readouterr().out
    assert "claude (project) — 1" in out
    assert "● fs  [stdio]  npx fs-server" in out
    # The other engines report an empty config.
    assert "codex (global): (none)" in out


def test_list_single_engine_argument_filters(monkeypatch, capsys):
    with patch(
        "core.services.mcp_service.list_servers", return_value=[]
    ) as list_servers:
        _run(monkeypatch, "mcp", "list", "codex")

    assert list_servers.call_args.args[0] == "codex"
    assert "codex (global): (none)" in capsys.readouterr().out


def test_list_surfaces_engine_errors_as_warnings(monkeypatch, capsys):
    def list_servers(engine, project_path):
        raise RuntimeError("config unreadable")

    with patch("core.services.mcp_service.list_servers", side_effect=list_servers):
        _run(monkeypatch, "mcp", "list", "claude")

    out = capsys.readouterr().out
    assert "claude" in out and "config unreadable" in out


# ── ca mcp add ───────────────────────────────────────────────────────────────


def test_add_stdio_server_reports_project_scope_for_claude(monkeypatch, capsys):
    with patch("core.services.mcp_service.add_server") as add_server:
        _run(monkeypatch, "mcp", "add", "claude", "fs", "npx", "fs-server")

    assert add_server.call_args.args[:3] == ("claude", str(Path.cwd()), "fs")
    assert add_server.call_args.kwargs["command"] == ["npx", "fs-server"]
    assert add_server.call_args.kwargs["env"] is None
    out = capsys.readouterr().out
    assert "[OK] Added 'fs' to claude (project scope)" in out
    assert "ca mcp sync claude" in out


def test_add_url_server_with_env_and_transport(monkeypatch, capsys):
    with patch("core.services.mcp_service.add_server") as add_server:
        _run(
            monkeypatch,
            "mcp", "add", "codex", "remote",
            "--url", "http://127.0.0.1:9000",
            "--env", "TOKEN=abc",
            "--env", "MODE=fast",
            "--transport", "http",
        )

    kwargs = add_server.call_args.kwargs
    assert kwargs["command"] is None
    assert kwargs["url"] == "http://127.0.0.1:9000"
    assert kwargs["env"] == {"TOKEN": "abc", "MODE": "fast"}
    assert kwargs["transport"] == "http"
    assert "(global scope)" in capsys.readouterr().out


def test_add_rejects_env_pairs_without_equals(monkeypatch, capsys):
    with patch("core.services.mcp_service.add_server") as add_server:
        with pytest.raises(SystemExit) as excinfo:
            _run(monkeypatch, "mcp", "add", "claude", "fs", "npx", "--env", "BROKEN")
    assert excinfo.value.code == 1
    add_server.assert_not_called()
    assert "--env expects KEY=VALUE, got: BROKEN" in capsys.readouterr().out


def test_add_service_error_exits_nonzero(monkeypatch, capsys):
    with patch(
        "core.services.mcp_service.add_server", side_effect=ValueError("bad name")
    ):
        with pytest.raises(SystemExit) as excinfo:
            _run(monkeypatch, "mcp", "add", "claude", "fs", "npx")
    assert excinfo.value.code == 1
    assert "[X] bad name" in capsys.readouterr().out


# ── ca mcp remove ────────────────────────────────────────────────────────────


def test_remove_success(monkeypatch, capsys):
    with patch("core.services.mcp_service.remove_server") as remove_server:
        _run(monkeypatch, "mcp", "remove", "codex", "fs")
    assert remove_server.call_args.args[0] == "codex"
    assert "[OK] Removed 'fs' from codex" in capsys.readouterr().out


def test_remove_unknown_server_exits(monkeypatch, capsys):
    with patch(
        "core.services.mcp_service.remove_server", side_effect=KeyError("fs")
    ):
        with pytest.raises(SystemExit) as excinfo:
            _run(monkeypatch, "mcp", "remove", "codex", "fs")
    assert excinfo.value.code == 1
    assert "[X] No such MCP server in codex: fs" in capsys.readouterr().out


# ── ca mcp sync ──────────────────────────────────────────────────────────────


def test_sync_prints_per_engine_actions(monkeypatch, capsys):
    results = [
        {"engine": "codex", "name": "fs", "action": "added", "detail": "new"},
        {"engine": "codex", "name": "web", "action": "skipped", "detail": "exists"},
        {"engine": "claude", "name": "fs", "action": "replaced", "detail": "overwritten"},
    ]
    with patch("core.services.mcp_service.sync_servers", return_value=results) as sync:
        _run(monkeypatch, "mcp", "sync", "opencode", "--overwrite")

    assert sync.call_args.kwargs["overwrite"] is True
    assert sync.call_args.kwargs["dry_run"] is False
    out = capsys.readouterr().out
    assert "+ fs — new" in out
    assert "= web — exists" in out
    assert "~ fs — overwritten" in out


def test_sync_dry_run_flags_and_passes_filters(monkeypatch, capsys):
    results = [{"engine": "codex", "name": "fs", "action": "added", "detail": "new"}]
    with patch("core.services.mcp_service.sync_servers", return_value=results) as sync:
        _run(
            monkeypatch, "mcp", "sync", "claude",
            "--to", "codex", "--name", "fs", "--dry-run",
        )
    kwargs = sync.call_args.kwargs
    assert kwargs["targets"] == ["codex"]
    assert kwargs["names"] == ["fs"]
    assert kwargs["dry_run"] is True
    out = capsys.readouterr().out
    assert "Dry run" in out


def test_sync_nothing_to_sync(monkeypatch, capsys):
    with patch("core.services.mcp_service.sync_servers", return_value=[]):
        _run(monkeypatch, "mcp", "sync", "claude")
    assert "Nothing to sync" in capsys.readouterr().out


def test_sync_partial_failure_exits(monkeypatch, capsys):
    results = [
        {"engine": "codex", "name": "fs", "action": "added", "detail": "new"},
        {"engine": "codex", "name": "web", "action": "failed", "detail": "read-only"},
    ]
    with patch("core.services.mcp_service.sync_servers", return_value=results):
        with pytest.raises(SystemExit) as excinfo:
            _run(monkeypatch, "mcp", "sync", "claude")
    assert excinfo.value.code == 1
    assert "1 of 2 operations failed." in capsys.readouterr().out


def test_sync_invalid_source_is_rejected_by_click(monkeypatch, capsys):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "mcp", "sync", "gpt5")


# ── ca mcp serve ─────────────────────────────────────────────────────────────


def test_serve_defaults_to_stdio(monkeypatch):
    with patch("core.services.mcp_server_service.serve") as serve:
        _run(monkeypatch, "mcp", "serve")
    assert serve.call_args.kwargs["transport"] == "stdio"
    assert serve.call_args.kwargs["port"] == 8525


def test_serve_http_with_port_and_group(monkeypatch):
    with patch("core.services.mcp_server_service.serve") as serve:
        _run(monkeypatch, "mcp", "serve", "--http", "--port", "9000", "--group", "work")
    kwargs = serve.call_args.kwargs
    assert kwargs["transport"] == "http"
    assert kwargs["port"] == 9000
    assert kwargs["group"] == "work"


def test_serve_runtime_error_exits(monkeypatch, capsys):
    with patch(
        "core.services.mcp_server_service.serve",
        side_effect=RuntimeError("port taken"),
    ):
        with pytest.raises(SystemExit) as excinfo:
            _run(monkeypatch, "mcp", "serve", "--http")
    assert excinfo.value.code == 1
    assert "port taken" in capsys.readouterr().out
