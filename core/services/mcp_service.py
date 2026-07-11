"""MCP server management, per engine.

Mutations (add/remove) shell out to each engine's own ``mcp`` CLI
subcommand wherever it works reliably — matching this project's core
architecture of wrapping official CLIs rather than reimplementing their
config formats. Reads parse each engine's native config file directly
(read-only, so there's no corruption risk), since none of the four CLIs'
``mcp list`` output is cleanly machine-parseable (health-check text,
account-level entries mixed with project entries, etc).

Two engines needed a fallback confirmed by a live pre-build spike — see
docs/mcp-cli-spike-results.md for the full transcript:
  - ``gemini mcp remove`` reproducibly fails to find entries even
    immediately after ``add`` in a fresh project. Removal falls back to
    directly editing ``.gemini/settings.json``.
  - ``opencode`` has no ``mcp remove`` subcommand at all (only
    ``add``/``list``/``auth``/``logout``/``debug``). Removal falls back to
    directly editing ``opencode.json``.

Scope also differs by engine, confirmed live (not assumed from --help):
  - claude, gemini: per-project (``<project>/.mcp.json``,
    ``<project>/.gemini/settings.json``).
  - codex, opencode: global, regardless of cwd (``~/.codex/config.toml``,
    ``~/.config/opencode/opencode.json``) — the CLIs have no project-scope
    flag for MCP servers in this version.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

_VALID_ENGINES = {"claude", "codex", "gemini", "opencode"}
_SAFE_NAME_RE = re.compile(r"^[\w.-]+$")


def _validate_engine(engine: str) -> None:
    if engine not in _VALID_ENGINES:
        raise ValueError(f"Invalid engine: {engine!r}")


def _validate_name(name: str) -> None:
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(f"Invalid MCP server name: {name!r}")


# --- Native config file locations -----------------------------------------


def _claude_mcp_path(project: Path) -> Path:
    return project / ".mcp.json"


def _gemini_settings_path(project: Path) -> Path:
    return project / ".gemini" / "settings.json"


def _codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def _opencode_config_path() -> Path:
    return Path.home() / ".config" / "opencode" / "opencode.json"


# --- Generic JSON read/write helpers ---------------------------------------


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _remove_key(path: Path, top_key: str, name: str) -> None:
    """Pops one server entry from a native config file, preserving everything else."""
    data = _read_json(path)
    servers = data.get(top_key, {})
    if name not in servers:
        raise KeyError(f"MCP server not found: {name!r}")
    del servers[name]
    data[top_key] = servers
    _atomic_write_json(path, data)


def _normalize_entry(name: str, scope: str, cfg: dict) -> dict:
    """Maps one engine-native server config dict to a uniform shape.

    Handles claude/gemini's ``{"command": str, "args": [...], "env": {...}}``,
    codex's TOML-derived equivalent, and opencode's
    ``{"command": [...combined...], "environment": {...}}`` — all four in
    one place rather than four near-duplicate normalizers.
    """
    command = cfg.get("command")
    args = cfg.get("args", [])
    if isinstance(command, list):
        full_command = command
    elif command:
        full_command = [command, *args]
    else:
        full_command = None
    url = cfg.get("url") or cfg.get("httpUrl")
    transport = cfg.get("type") or (
        "http" if url else "stdio" if full_command else "unknown"
    )
    env = cfg.get("env") or cfg.get("environment") or {}
    return {
        "name": name,
        "scope": scope,
        "transport": transport,
        "command": full_command,
        "url": url,
        "env": env,
    }


# --- Per-engine reads --------------------------------------------------


def _server_entries(container: object) -> list[tuple[str, Any]]:
    """Defensively coerces a config file's server-map value into
    (name, cfg) pairs, tolerating a malformed config where the expected
    key isn't actually a mapping (e.g. hand-edited into a list or scalar).

    ``cfg`` is left untyped (``Any``) rather than ``dict`` — codex's caller
    needs it to still be a tomlkit ``Table`` so ``.unwrap()`` works.
    """
    if not hasattr(container, "items"):
        return []
    return list(container.items())  # type: ignore[attr-defined]


def _list_claude(project: Path) -> list[dict]:
    servers = _read_json(_claude_mcp_path(project)).get("mcpServers", {})
    return [
        _normalize_entry(name, "project", cfg) for name, cfg in _server_entries(servers)
    ]


def _list_codex() -> list[dict]:
    import tomlkit

    path = _codex_config_path()
    if not path.exists():
        return []
    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    servers = doc.get("mcp_servers", {})
    return [
        _normalize_entry(name, "global", cfg.unwrap())
        for name, cfg in _server_entries(servers)
    ]


def _list_gemini(project: Path) -> list[dict]:
    servers = _read_json(_gemini_settings_path(project)).get("mcpServers", {})
    return [
        _normalize_entry(name, "project", cfg) for name, cfg in _server_entries(servers)
    ]


def _list_opencode() -> list[dict]:
    servers = _read_json(_opencode_config_path()).get("mcp", {})
    return [
        _normalize_entry(name, "global", cfg) for name, cfg in _server_entries(servers)
    ]


def list_servers(engine: str, project_path: str) -> list[dict]:
    """Lists configured MCP servers for one engine, read from its native config."""
    _validate_engine(engine)
    project = Path(project_path)
    if engine == "claude":
        return _list_claude(project)
    if engine == "codex":
        return _list_codex()
    if engine == "gemini":
        return _list_gemini(project)
    return _list_opencode()


# --- Mutations: shell out to each engine's own mcp CLI ---------------------


def _run_cli(cmd: list[str], cwd: str) -> None:
    executable = shutil.which(cmd[0])
    if executable is None:
        raise RuntimeError(f"{cmd[0]!r} CLI not found on PATH")
    try:
        result = subprocess.run(
            [executable, *cmd[1:]],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{cmd[0]} timed out after 20 seconds") from exc
    except OSError as exc:
        raise RuntimeError(f"Failed to run {cmd[0]}: {exc}") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(message or f"{cmd[0]} exited with code {result.returncode}")


def _build_add_command(
    engine: str,
    name: str,
    command: Optional[list[str]],
    url: Optional[str],
    env_pairs: list[str],
    transport: Optional[str],
) -> list[str]:
    """Builds each engine's ``mcp add`` invocation using the exact flag
    ordering confirmed live by the pre-build spike (see module docstring).
    Remote/URL servers follow the same documented flag shape but weren't
    live-spiked (only stdio/local servers were).
    """
    if engine == "claude":
        # -e/--env is variadic (consumes tokens until the next flag or --),
        # so it must come *after* the positional <name> or it swallows it —
        # confirmed live: putting -e before name made claude parse the name
        # itself as another env-var value and reject the whole command.
        cmd = ["claude", "mcp", "add", "--scope", "project"]
        if transport:
            cmd += ["--transport", transport]
        cmd.append(name)
        for pair in env_pairs:
            cmd += ["-e", pair]
        cmd.append(url if url else "--")
        if command:
            cmd += command
        return cmd

    if engine == "codex":
        cmd = ["codex", "mcp", "add", name]
        for pair in env_pairs:
            cmd += ["--env", pair]
        if url:
            cmd += ["--url", url]
        else:
            cmd.append("--")
            cmd += command or []
        return cmd

    if engine == "gemini":
        # Same variadic -e/--env ordering hazard as claude — name must come
        # before the -e flags.
        cmd = ["gemini", "mcp", "add", "--scope", "project"]
        if transport:
            cmd += ["--transport", transport]
        cmd.append(name)
        for pair in env_pairs:
            cmd += ["-e", pair]
        if url:
            cmd.append(url)
        else:
            cmd += command or []
        return cmd

    # opencode
    cmd = ["opencode", "mcp", "add", name]
    for pair in env_pairs:
        cmd += ["--env", pair]
    if url:
        cmd += ["--url", url]
    else:
        cmd.append("--")
        cmd += command or []
    return cmd


def add_server(
    engine: str,
    project_path: str,
    name: str,
    command: Optional[list[str]] = None,
    url: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    transport: Optional[str] = None,
) -> None:
    """Adds an MCP server via the engine's own ``mcp add`` CLI subcommand."""
    _validate_engine(engine)
    _validate_name(name)
    if bool(command) == bool(url):
        raise ValueError("Exactly one of command or url must be provided")

    env_pairs = [f"{k}={v}" for k, v in (env or {}).items()]
    cmd = _build_add_command(engine, name, command, url, env_pairs, transport)
    _run_cli(cmd, cwd=project_path)


def remove_server(engine: str, project_path: str, name: str) -> None:
    """Removes an MCP server — via CLI where it works, via direct config-file
    edit for gemini/opencode, where the spike found the CLI path broken or
    absent (see module docstring)."""
    _validate_engine(engine)
    _validate_name(name)

    if engine == "claude":
        _run_cli(["claude", "mcp", "remove", name], cwd=project_path)
    elif engine == "codex":
        _run_cli(["codex", "mcp", "remove", name], cwd=project_path)
    elif engine == "gemini":
        _remove_key(_gemini_settings_path(Path(project_path)), "mcpServers", name)
    else:
        _remove_key(_opencode_config_path(), "mcp", name)
