"""MCP server management, per engine.

Mutations (add/remove) shell out to each engine's own ``mcp`` CLI
subcommand wherever it works reliably — matching this project's core
architecture of wrapping official CLIs rather than reimplementing their
config formats. Reads parse each engine's native config file directly
(read-only, so there's no corruption risk), since none of the four CLIs'
``mcp list`` output is cleanly machine-parseable (health-check text,
account-level entries mixed with project entries, etc).

One engine needed a fallback confirmed by a live pre-build spike — see
docs/mcp-cli-spike-results.md for the full transcript:
  - ``opencode`` has no ``mcp remove`` subcommand at all (only
    ``add``/``list``/``auth``/``logout``/``debug``). Removal falls back to
    directly editing ``opencode.json``.

Scope also differs by engine, confirmed live (not assumed from --help):
  - claude: per-project (``<project>/.mcp.json``).
  - codex, opencode: global, regardless of cwd (``~/.codex/config.toml``,
    ``~/.config/opencode/opencode.{jsonc,json}``) — the CLIs have no
    project-scope flag for MCP servers in this version. opencode 1.18 writes
    the ``.jsonc`` variant, so both names are resolved and JSONC comments are
    tolerated on read.

:func:`sync_servers` copies definitions between engines by replaying them
through these same per-engine add/remove paths, so each engine keeps writing
its own native format and no config file is ever copied across.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from core.constants import ENGINES

_SAFE_NAME_RE = re.compile(r"^[\w.-]+$")


def _validate_engine(engine: str) -> None:
    if engine not in ENGINES:
        raise ValueError(f"Invalid engine: {engine!r}")


def _validate_name(name: str) -> None:
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(f"Invalid MCP server name: {name!r}")


# --- Native config file locations -----------------------------------------


def _claude_mcp_path(project: Path) -> Path:
    return project / ".mcp.json"


def _codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


_OPENCODE_CONFIG_NAMES = ("opencode.jsonc", "opencode.json")


def _opencode_config_path() -> Path:
    """Resolves opencode's global config, which may be ``.jsonc`` or ``.json``.

    opencode 1.18 writes ``opencode.jsonc``; ``opencode.json`` is equally
    valid and is what hand-written setups tend to use. Whichever exists wins
    — checking only one name made every opencode server invisible to reads
    on a default install.

    When neither exists the ``.jsonc`` path is returned as the nominal
    location; nothing here creates the file, so this only affects the error
    message a caller sees.
    """
    config_dir = Path.home() / ".config" / "opencode"
    for name in _OPENCODE_CONFIG_NAMES:
        candidate = config_dir / name
        if candidate.exists():
            return candidate
    return config_dir / _OPENCODE_CONFIG_NAMES[0]


# --- Generic JSON read/write helpers ---------------------------------------


def _strip_jsonc_comments(text: str) -> str:
    """Removes ``//`` and ``/* */`` comments that fall outside string literals.

    Scans character by character rather than using a regex so that a ``//``
    inside a value like ``"https://example.com"`` is not mistaken for the
    start of a comment.
    """
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        char = text[i]
        if in_string:
            out.append(char)
            if char == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            i += 1
            continue
        if char == "/" and i + 1 < n:
            if text[i + 1] == "/":
                while i < n and text[i] != "\n":
                    i += 1
                continue
            if text[i + 1] == "*":
                i += 2
                while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i += 2
                continue
        out.append(char)
        i += 1
    return "".join(out)


def _read_json(path: Path) -> dict:
    """Reads a config file, tolerating JSONC comments.

    opencode's config is routinely a ``.jsonc``; without the comment-stripping
    fallback a commented file parses as empty and its servers silently vanish
    from every read. A file that is still unparseable afterwards keeps the
    existing tolerant behaviour of reading as empty.
    """
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_strip_jsonc_comments(raw))
    except json.JSONDecodeError:
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


def _has_jsonc_comments(path: Path) -> bool:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return _strip_jsonc_comments(raw) != raw


def _remove_key(path: Path, top_key: str, name: str) -> None:
    """Pops one server entry from a native config file, preserving everything else."""
    data = _read_json(path)
    servers = data.get(top_key, {})
    if name not in servers:
        raise KeyError(f"MCP server not found: {name!r}")

    # Rewriting the file as plain JSON would silently delete any comments the
    # user wrote, so refuse rather than destroy them.
    if _has_jsonc_comments(path):
        raise RuntimeError(
            f"{path} contains comments, which would be lost by rewriting it. "
            f"Remove the {name!r} entry from that file by hand instead."
        )

    del servers[name]
    data[top_key] = servers
    _atomic_write_json(path, data)


def _normalize_entry(name: str, scope: str, cfg: dict) -> dict:
    """Maps one engine-native server config dict to a uniform shape.

    Handles claude's ``{"command": str, "args": [...], "env": {...}}``,
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


def _list_opencode() -> list[dict]:
    servers = _read_json(_opencode_config_path()).get("mcp", {})
    return [
        _normalize_entry(name, "global", cfg) for name, cfg in _server_entries(servers)
    ]


def _list_codebuddy(project: Path) -> list[dict]:
    # Project scope lives in ``<project>/.mcp.json`` under ``mcpServers``
    # (verified live: ``codebuddy mcp add <name> -s project -- ...`` writes
    # entries shaped ``{"command": str, "args": [...], "type": "stdio"}``).
    # User scope (``~/.codebuddy/.mcp.json``) is intentionally not merged,
    # mirroring how the other engines surface project scope only.
    servers = _read_json(project / ".mcp.json").get("mcpServers", {})
    return [
        _normalize_entry(name, "project", cfg) for name, cfg in _server_entries(servers)
    ]


def list_servers(engine: str, project_path: str) -> list[dict]:
    """Lists configured MCP servers for one engine, read from its native config."""
    _validate_engine(engine)
    project = Path(project_path)
    if engine == "claude":
        return _list_claude(project)
    if engine == "codex":
        return _list_codex()
    if engine == "codebuddy":
        return _list_codebuddy(project)
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
            encoding="utf-8",
            errors="replace",
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
    command: list[str] | None,
    url: str | None,
    env_pairs: list[str],
    transport: str | None,
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

    if engine == "codebuddy":
        # ``codebuddy mcp add [options] <name> <commandOrUrl> [args...]`` with
        # ``-s/--scope`` (local|project|user), ``-t/--transport``
        # (stdio|sse|http) and the same variadic ``-e/--env`` ordering hazard
        # as claude — name before the -e flags, ``--`` before the
        # command (verified live).
        cmd = ["codebuddy", "mcp", "add", "-s", "project"]
        if transport:
            cmd += ["-t", transport]
        cmd.append(name)
        for pair in env_pairs:
            cmd += ["-e", pair]
        cmd.append(url if url else "--")
        if command:
            cmd += command
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
    command: list[str] | None = None,
    url: str | None = None,
    env: dict[str, str] | None = None,
    transport: str | None = None,
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
    edit for opencode, where the spike found the CLI path absent (see module
    docstring)."""
    _validate_engine(engine)
    _validate_name(name)

    if engine == "claude":
        _run_cli(["claude", "mcp", "remove", name], cwd=project_path)
    elif engine == "codex":
        _run_cli(["codex", "mcp", "remove", name], cwd=project_path)
    elif engine == "codebuddy":
        _run_cli(
            ["codebuddy", "mcp", "remove", name, "-s", "project"], cwd=project_path
        )
    else:
        _remove_key(_opencode_config_path(), "mcp", name)


# --- Cross-engine sync -----------------------------------------------------


def _sync_add_kwargs(entry: dict) -> dict:
    """Maps a normalized entry back into ``add_server()`` keyword arguments.

    Transport strings are engine-specific — opencode writes ``local``/``remote``
    where claude writes ``stdio``/``http``/``sse`` — so the source engine's raw
    value is never forwarded as-is. It is reduced to the stdio-vs-remote split
    and re-expressed in the terms ``add_server()`` accepts, with ``None`` for
    stdio servers since that is every engine's default.
    """
    url = entry.get("url")
    command = entry.get("command")
    env = entry.get("env") or {}

    if url:
        raw = str(entry.get("transport") or "").lower()
        return {"url": url, "transport": "sse" if raw == "sse" else "http", "env": env}
    if command:
        return {"command": list(command), "transport": None, "env": env}
    raise ValueError("entry has neither a command nor a url")


def sync_servers(
    source_engine: str,
    project_path: str,
    targets: list[str] | None = None,
    names: list[str] | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> list[dict]:
    """Copies MCP server definitions from one engine's config to the others.

    Each server is re-added through the target engine's own ``add_server()``
    path, so every engine still writes its own native format — this never
    copies config files across.

    One engine failing (its CLI missing from PATH, say) does not abort the
    rest: each attempt is recorded individually so a partial sync is visible
    rather than silent. Note that codex and opencode are global-scoped, so
    syncing *into* them writes outside ``project_path``.

    Args:
        source_engine: Engine to read definitions from.
        project_path: Project directory; load-bearing only for claude.
        targets: Engines to write to. Defaults to every engine but the source.
        names: Only sync these servers. Defaults to all of the source's.
        overwrite: Replace a same-named server in the target instead of
            skipping it.
        dry_run: Report the actions that would be taken without running them.

    Returns:
        One record per (target engine, server) pair, each with ``engine``,
        ``name``, ``action`` (``added``/``replaced``/``skipped``/``failed``)
        and a human-readable ``detail``.
    """
    _validate_engine(source_engine)

    if targets is None:
        target_engines = sorted(ENGINES - {source_engine})
    else:
        target_engines = list(dict.fromkeys(targets))
        for target in target_engines:
            _validate_engine(target)
            if target == source_engine:
                raise ValueError(
                    f"Cannot sync {source_engine!r} onto itself; "
                    "drop it from the target list"
                )

    available = {
        entry["name"]: entry for entry in list_servers(source_engine, project_path)
    }
    if names is None:
        selected = list(available.values())
    else:
        missing = [name for name in names if name not in available]
        if missing:
            raise ValueError(
                f"No such MCP server in {source_engine}: {', '.join(sorted(missing))}"
            )
        selected = [available[name] for name in dict.fromkeys(names)]

    results: list[dict] = []
    for target in target_engines:
        try:
            existing = {entry["name"] for entry in list_servers(target, project_path)}
        except Exception as exc:  # a target's config being unreadable is not fatal
            for entry in selected:
                results.append(
                    {
                        "engine": target,
                        "name": entry["name"],
                        "action": "failed",
                        "detail": f"could not read {target} config: {exc}",
                    }
                )
            continue

        for entry in selected:
            results.append(
                _sync_one(target, project_path, entry, existing, overwrite, dry_run)
            )

    return results


def _sync_one(
    target: str,
    project_path: str,
    entry: dict,
    existing: set[str],
    overwrite: bool,
    dry_run: bool,
) -> dict:
    """Syncs a single server into a single target, never raising."""
    name = entry["name"]

    def record(action: str, detail: str) -> dict:
        return {"engine": target, "name": name, "action": action, "detail": detail}

    present = name in existing
    if present and not overwrite:
        return record("skipped", "already configured; pass overwrite to replace it")

    try:
        kwargs = _sync_add_kwargs(entry)
    except ValueError as exc:
        return record("failed", str(exc))

    if dry_run:
        return record(
            "replaced" if present else "added",
            "would replace existing entry" if present else "would be added",
        )

    if present:
        try:
            remove_server(target, project_path, name)
        except Exception as exc:
            return record("failed", f"could not remove existing entry: {exc}")

    try:
        add_server(target, project_path, name, **kwargs)
    except Exception as exc:
        if present:
            # The old entry is already gone at this point, so say so rather
            # than let the user assume the target was left untouched.
            return record("failed", f"removed existing entry but re-add failed: {exc}")
        return record("failed", str(exc))

    return record("replaced" if present else "added", "ok")
