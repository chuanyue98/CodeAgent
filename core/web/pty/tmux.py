"""tmux-backed session hosting and lifecycle management for POSIX systems."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.web.pty.common import SpawnError

_TMUX_SOCKET_ENV = "CA_PTY_TMUX_SOCKET"
_DEFAULT_TMUX_SOCKET = "codeagent"

# 活跃 PTY 会话注册表，供实例管理页（routers/instances.py）列出与停止。
# 只在事件循环内读写，普通 dict 即可。
_ACTIVE_SESSIONS: dict[str, dict[str, Any]] = {}

# The browser tab id that names a fresh terminal's tmux session. It is only
# hashed, never passed to a shell, but a bounded charset keeps it a key.
_TAB_KEY_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_MIN_COLS, _MAX_COLS = 2, 1000
_MIN_ROWS, _MAX_ROWS = 2, 500

# 概览页启动引擎时带的首条提示。
_PENDING_PROMPTS: dict[str, tuple[str, float]] = {}
_PROMPT_TTL_SECONDS = 60.0
_MAX_PROMPT_CHARS = 20_000


def _purge_expired_prompts(now: float) -> None:
    for key, (_prompt, stored_at) in list(_PENDING_PROMPTS.items()):
        if now - stored_at > _PROMPT_TTL_SECONDS:
            del _PENDING_PROMPTS[key]


def _stage_prompt(tab_key: str, prompt: str, *, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    _purge_expired_prompts(now)
    _PENDING_PROMPTS[tab_key] = (prompt, now)


def _take_prompt(tab_key: str | None, *, now: float | None = None) -> str | None:
    """Removes and returns the staged prompt for *tab_key*, if it is still fresh."""
    if tab_key is None:
        return None
    now = time.monotonic() if now is None else now
    _purge_expired_prompts(now)
    staged = _PENDING_PROMPTS.pop(tab_key, None)
    return staged[0] if staged else None


def _tmux_binary() -> str | None:
    """The tmux path, or None when POSIX-without-tmux / Windows."""
    if sys.platform == "win32":
        return None
    return shutil.which("tmux")


def _tmux_socket() -> str:
    """The dedicated tmux socket name (tests override via env)."""
    return os.environ.get(_TMUX_SOCKET_ENV, _DEFAULT_TMUX_SOCKET)


def _run_tmux(*args: str, timeout: float = 10) -> subprocess.CompletedProcess[str]:
    """Runs one tmux command on the dedicated socket, synchronously.

    The environment matches what a directly-spawned engine got (see
    _spawn_posix), so panes created on a fresh server inherit the same
    PATH/locale/credentials this server would have handed the engine.
    """
    binary = _tmux_binary()
    if binary is None:
        raise SpawnError("tmux is not available")
    return subprocess.run(
        [binary, "-L", _tmux_socket(), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _tmux_session_name(
    engine: str,
    working_dir: Path,
    session_id: str | None,
    tab_key: str | None = None,
) -> str:
    """The tmux session name for one browser terminal.

    Resumed engine sessions hash (engine, cwd, session id) so reopening the
    same deep link lands on the same running engine. A fresh terminal hashes
    the browser tab's own key instead: a reload or reconnect of that tab must
    land on the engine it already started, or every reconnect spawns another
    engine and strands the previous one in tmux. With neither, the name is
    unique so two tabs never share one engine.
    """
    if session_id:
        digest = hashlib.sha256(
            f"{engine}\0{working_dir}\0{session_id}".encode()
        ).hexdigest()[:12]
    elif tab_key:
        digest = hashlib.sha256(
            f"{engine}\0{working_dir}\0tab\0{tab_key}".encode()
        ).hexdigest()[:12]
    else:
        digest = uuid4().hex[:12]
    return f"ca-{engine}-{digest}"


def _tmux_ensure_session(
    name: str,
    engine_argv: list[str],
    working_dir: Path,
    cols: int = 80,
    rows: int = 24,
) -> None:
    """Creates the tmux session running *engine_argv* if it doesn't exist."""
    if _run_tmux("has-session", "-t", name).returncode == 0:
        return
    result = _run_tmux(
        "new-session",
        "-d",
        "-s",
        name,
        "-x",
        str(cols),
        "-y",
        str(rows),
        "-c",
        str(working_dir),
    )
    if result.returncode != 0:
        if _run_tmux("has-session", "-t", name).returncode == 0:
            return
        raise SpawnError(
            f"tmux new-session failed: {result.stderr.strip() or result.returncode}"
        )
    for args in (
        ("set-option", "-t", name, "remain-on-exit", "on"),
        (
            "set-hook",
            "-t",
            name,
            "pane-died",
            f"run-shell 'tmux -L {_tmux_socket()} detach-client -s {name}'",
        ),
        ("set-option", "-t", name, "status", "off"),
        ("set-option", "-t", name, "escape-time", "10"),
        ("set-option", "-t", name, "history-limit", "10000"),
    ):
        _run_tmux(*args)
    result = _run_tmux(
        "respawn-pane",
        "-k",
        "-t",
        name,
        "-c",
        str(working_dir),
        shlex.join(engine_argv),
    )
    if result.returncode != 0:
        with contextlib.suppress(Exception):
            _run_tmux("kill-session", "-t", name)
        raise SpawnError(
            f"tmux respawn-pane failed: {result.stderr.strip() or result.returncode}"
        )


def _tmux_has_session(name: str) -> bool:
    return _run_tmux("has-session", "-t", name).returncode == 0


def _tmux_engine_gone(name: str) -> bool:
    result = _run_tmux("display-message", "-p", "-t", name, "#{pane_dead}")
    return result.returncode != 0 or result.stdout.strip() == "1"


def _tmux_kill_session(name: str) -> None:
    _run_tmux("kill-session", "-t", name)


def _tmux_pane_pid(name: str) -> int | None:
    result = _run_tmux("display-message", "-p", "-t", name, "#{pane_pid}")
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def kill_tmux_server() -> None:
    """Kills the dedicated tmux server (lifespan startup/shutdown hook)."""
    if _tmux_binary() is None:
        return
    with contextlib.suppress(Exception):
        _run_tmux("kill-server", timeout=5)


_TMUX_WATCHDOG_SCRIPT = (
    'while kill -0 "$1" 2>/dev/null; do sleep 2; done; '
    '"$2" -L "$3" kill-server 2>/dev/null'
)


def start_tmux_watchdog(pid: int | None = None) -> None:
    """Takes the tmux server down once *pid* (this process) is gone, however it died."""
    binary = _tmux_binary()
    if binary is None:
        return
    with contextlib.suppress(OSError):
        subprocess.Popen(
            [
                "/bin/sh",
                "-c",
                _TMUX_WATCHDOG_SCRIPT,
                "ca-tmux-watchdog",
                str(pid or os.getpid()),
                binary,
                _tmux_socket(),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def list_active_sessions() -> list[dict[str, Any]]:
    """返回活跃 PTY 会话的可序列化信息（不含会话对象本身）。"""
    return [
        {key: value for key, value in entry.items() if key != "session"}
        for entry in _ACTIVE_SESSIONS.values()
    ]


async def prune_detached_sessions() -> None:
    """Drops registry entries whose engine has exited while detached."""
    for pty_id, entry in list(_ACTIVE_SESSIONS.items()):
        if entry.get("session") is not None:
            continue
        name = entry.get("tmux_name")
        if not name:
            continue
        if await asyncio.to_thread(_tmux_engine_gone, name):
            await asyncio.to_thread(_tmux_kill_session, name)
            _ACTIVE_SESSIONS.pop(pty_id, None)


def _entry_for_tmux_name(name: str) -> dict[str, Any] | None:
    for entry in _ACTIVE_SESSIONS.values():
        if entry.get("tmux_name") == name:
            return entry
    return None


async def stop_active_session(session_id: str) -> bool:
    """终止一个活跃 PTY 会话；不存在时返回 False。"""
    entry = _ACTIVE_SESSIONS.get(session_id)
    if entry is None:
        return False
    session = entry.get("session")
    if session is not None:
        await session.shutdown()
    else:
        name = entry.get("tmux_name")
        if name:
            await asyncio.to_thread(_tmux_kill_session, name)
    _ACTIVE_SESSIONS.pop(session_id, None)
    return True
