"""MCP server management, per engine.

Mutations (add/remove) shell out to each engine's own ``mcp`` CLI
subcommand wherever it works reliably — matching this project's core
architecture of wrapping official CLIs rather than reimplementing their
config formats. Reads parse each engine's native config file directly
(read-only, so there's no corruption risk), since none of the four CLIs'
``mcp list`` output is cleanly machine-parseable (health-check text,
account-level entries mixed with project entries, etc).

One engine needed a fallback confirmed by a live pre-build spike:
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
from pathlib import Path
from typing import Any

from core.constants import ENGINES, normalize_engine_name
from core.host_env import child_environ
from core.logging_config import get_logger
from core.utils.atomic_write import atomic_write
from engines.codex_home import user_codex_home

logger = get_logger(__name__)

_SAFE_NAME_RE = re.compile(r"^[\w.-]+$")


def _validate_engine(engine: str) -> str:
    canonical = normalize_engine_name(engine)
    if canonical not in ENGINES:
        raise ValueError(f"Invalid engine: {engine!r}")
    return canonical


def _validate_name(name: str) -> None:
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(f"Invalid MCP server name: {name!r}")


# --- Native config file locations -----------------------------------------


def _claude_mcp_path(project: Path) -> Path:
    return project / ".mcp.json"


def _codex_config_path() -> Path:
    return user_codex_home() / "config.toml"


def _antigravity_config_path() -> Path:
    return Path.home() / ".gemini" / "config" / "mcp_config.json"


_OPENCODE_CONFIG_NAMES = ("opencode.jsonc", "opencode.json")


def _opencode_config_path() -> Path:
    """解析 OpenCode 全局配置文件路径，兼容环境变量覆盖与 ``.jsonc`` / ``.json``。"""
    explicit_file = os.environ.get("OPENCODE_CONFIG", "").strip()
    if explicit_file:
        return Path(explicit_file).expanduser()
    configured_dir = os.environ.get("OPENCODE_CONFIG_DIR", "").strip()
    if configured_dir:
        config_dir = Path(configured_dir).expanduser()
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME", "").strip()
        config_dir = (
            Path(xdg_config).expanduser() if xdg_config else Path.home() / ".config"
        ) / "opencode"
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


def _read_json(path: Path, *, strict: bool = False) -> dict:
    """读取 JSON/JSONC 配置文件；``strict=True`` 时拒绝将损坏配置视为空对象。"""
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        if strict:
            raise RuntimeError(f"无法读取配置文件 {path}: {exc}") from exc
        logger.warning("读取 %s 失败，MCP 列表按空处理: %s", path, exc)
        return {}
    parsed: Any = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as first_exc:
        try:
            parsed = json.loads(_strip_jsonc_comments(raw))
        except json.JSONDecodeError as exc:
            if strict:
                raise RuntimeError(
                    f"配置文件 {path} JSON 格式损坏，拒绝覆盖: {first_exc}"
                ) from exc
            logger.warning("解析 %s 失败，MCP 列表按空处理: %s", path, first_exc)
            return {}
    if not isinstance(parsed, dict):
        if strict:
            raise RuntimeError(f"配置文件 {path} 顶层不是 JSON 对象，拒绝覆盖")
        logger.warning("配置文件 %s 顶层不是 JSON 对象，MCP 列表按空处理", path)
        return {}
    return parsed


def _atomic_write_json(path: Path, data: dict) -> None:
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False), fsync=True)


def _has_jsonc_comments(path: Path) -> bool:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return False
    return _strip_jsonc_comments(raw) != raw


def _remove_key(path: Path, top_key: str, name: str) -> None:
    """从原生配置文件中移除指定 MCP 条目，损坏配置直接报错而不覆盖。"""
    data = _read_json(path, strict=True)
    if top_key not in data:
        raise KeyError(f"MCP server not found: {name!r}")
    servers = data[top_key]
    if not isinstance(servers, dict):
        raise RuntimeError(f"配置文件 {path} 中 {top_key!r} 不是对象，拒绝修改")
    if name not in servers:
        raise KeyError(f"MCP server not found: {name!r}")

    # 直接以标准 JSON 重写会丢失用户注释，检测到注释时拒绝修改。
    if _has_jsonc_comments(path):
        raise RuntimeError(
            f"{path} contains comments, which would be lost by rewriting it. "
            f"Remove the {name!r} entry from that file by hand instead."
        )

    del servers[name]
    data[top_key] = servers
    _atomic_write_json(path, data)


def _normalize_entry(name: str, scope: str, cfg: object) -> dict:
    """将各引擎原生 MCP 配置条目归一化为统一结构，并防护畸形字段。"""
    if not isinstance(cfg, dict):
        return {
            "name": name,
            "scope": scope,
            "transport": "unknown",
            "command": None,
            "url": None,
            "env": {},
        }
    command = cfg.get("command")
    raw_args = cfg.get("args")
    if isinstance(raw_args, (list, tuple)):
        args = [str(item) for item in raw_args]
    elif isinstance(raw_args, str) and raw_args:
        args = [raw_args]
    else:
        args = []

    if isinstance(command, list):
        full_command: list[str] | None = [str(item) for item in command] or None
    elif isinstance(command, str) and command:
        full_command = [command, *args]
    else:
        full_command = None

    raw_url = cfg.get("url") or cfg.get("httpUrl") or cfg.get("serverUrl")
    url = raw_url if isinstance(raw_url, str) and raw_url else None
    raw_transport = cfg.get("type")
    transport = (
        str(raw_transport)
        if isinstance(raw_transport, str) and raw_transport
        else ("http" if url else "stdio" if full_command else "unknown")
    )
    raw_env = cfg.get("env")
    if not isinstance(raw_env, dict):
        raw_env = cfg.get("environment")
    env = (
        {str(k): str(v) for k, v in raw_env.items()}
        if isinstance(raw_env, dict)
        else {}
    )
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
        # 配置损坏时静默返回空列表会让 drift 检测把"有"报成"无"，
        # 至少要把原因留在日志里。
        logger.warning("解析 %s 失败，MCP 列表按空处理", path, exc_info=True)
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


def _list_antigravity() -> list[dict]:
    servers = _read_json(_antigravity_config_path()).get("mcpServers", {})
    return [
        _normalize_entry(name, "user", cfg) for name, cfg in _server_entries(servers)
    ]


def list_servers(engine: str, project_path: str) -> list[dict]:
    """Lists configured MCP servers for one engine, read from its native config."""
    canonical = _validate_engine(engine)
    project = Path(project_path)
    if canonical == "claude":
        return _list_claude(project)
    if canonical == "codex":
        return _list_codex()
    if canonical == "codebuddy":
        return _list_codebuddy(project)
    if canonical == "antigravity":
        return _list_antigravity()
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
            env=child_environ(),
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

    if engine == "antigravity":
        cmd = ["agy", "mcp", "add"]
        for pair in env_pairs:
            cmd += ["--env", pair]
        cmd.append(name)
        if url:
            cmd.append(url)
        else:
            cmd.append("--")
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
    command: list[str] | None = None,
    url: str | None = None,
    env: dict[str, str] | None = None,
    transport: str | None = None,
) -> None:
    """Adds an MCP server via the engine's own ``mcp add`` CLI subcommand."""
    canonical = _validate_engine(engine)
    _validate_name(name)
    if bool(command) == bool(url):
        raise ValueError("Exactly one of command or url must be provided")

    env_pairs = [f"{k}={v}" for k, v in (env or {}).items()]
    cmd = _build_add_command(canonical, name, command, url, env_pairs, transport)
    _run_cli(cmd, cwd=project_path)


def remove_server(engine: str, project_path: str, name: str) -> None:
    """Removes an MCP server — via CLI where it works, via direct config-file
    edit for opencode, where the spike found the CLI path absent (see module
    docstring)."""
    canonical = _validate_engine(engine)
    _validate_name(name)

    if canonical == "claude":
        _run_cli(["claude", "mcp", "remove", name], cwd=project_path)
    elif canonical == "codex":
        _run_cli(["codex", "mcp", "remove", name], cwd=project_path)
    elif canonical == "codebuddy":
        _run_cli(
            ["codebuddy", "mcp", "remove", name, "-s", "project"], cwd=project_path
        )
    elif canonical == "antigravity":
        _run_cli(["agy", "mcp", "remove", name], cwd=project_path)
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
    raw_env = entry.get("env")
    env = raw_env if isinstance(raw_env, dict) else {}

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
    canonical_source = _validate_engine(source_engine)

    if targets is None:
        target_engines = sorted(ENGINES - {canonical_source})
    else:
        target_engines = list(dict.fromkeys(_validate_engine(t) for t in targets))
        for target in target_engines:
            if target == canonical_source:
                raise ValueError(
                    f"Cannot sync {canonical_source!r} onto itself; "
                    "drop it from the target list"
                )

    available = {
        entry["name"]: entry for entry in list_servers(canonical_source, project_path)
    }
    if names is None:
        selected = list(available.values())
    else:
        missing = [name for name in names if name not in available]
        if missing:
            raise ValueError(
                f"No such MCP server in {canonical_source}: {', '.join(sorted(missing))}"
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
